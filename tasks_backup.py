# -*- coding: utf-8 -*-
#
# Copyright 2011 Google Inc.  All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# 27 Jan 2012;
# Google Tasks Backup (tasks-backup) created by Julie Smith, based on Google Tasks Porter

# pylint: disable=too-many-lines

"""Main web application handler for Google Tasks Backup."""

# Orig __author__ = "dwightguth@google.com (Dwight Guth)"
__author__ = "julie.smith.1999@gmail.com (Julie Smith)"



# ------------------------
# Standard library imports
# ------------------------
import logging
import os
import pickle
import gc
import time
import operator
import datetime

from collections import Counter
# from urlparse import urljoin


# ------------------------
# Google Appengine imports
# ------------------------
from google.appengine.api import mail
from google.appengine.api import taskqueue
from google.appengine.api import users
from google.appengine.api import mail_errors # To catch InvalidSenderError
from google.appengine.api import logservice # To flush logs
from google.appengine.api import urlfetch
from google.appengine.api.app_identity import get_application_id
from google.appengine.ext import db
from google.appengine.ext.webapp import template
from google.appengine.runtime import apiproxy_errors
import webapp2

# ----------------------------
# Application-specific imports
# ----------------------------
import model
import settings
# appversion.version is set before the upload process to keep the version number consistent
import appversion 
import host_settings
import shared # Code which is common between tasks-backup.py and worker.py
import constants

# ---------------------
# Local library imports
# ---------------------
# Import apiclient errors so that we can process HttpError
# from .apiclient import errors as apiclient_errors
from oauth2client.appengine import OAuth2Decorator




# Fix for DeadlineExceeded, because "Pre-Call Hooks to UrlFetch Not Working"
#     Based on code from https://groups.google.com/forum/#!msg/google-appengine/OANTefJvn0A/uRKKHnCKr7QJ # pylint: disable=line-too-long
real_fetch = urlfetch.fetch # pylint: disable=invalid-name
def fetch_with_deadline(url, *args, **argv):
    argv['deadline'] = settings.URL_FETCH_TIMEOUT
    return real_fetch(url, *args, **argv)
urlfetch.fetch = fetch_with_deadline





logservice.AUTOFLUSH_EVERY_SECONDS = 5
logservice.AUTOFLUSH_EVERY_BYTES = None
logservice.AUTOFLUSH_EVERY_LINES = 5
logservice.AUTOFLUSH_ENABLED = True


MSG = "Authorisation error. Please report this error to " + settings.url_issues_page

auth_decorator = OAuth2Decorator( # pylint: disable=invalid-name
                                 client_id=host_settings.CLIENT_ID,
                                 client_secret=host_settings.CLIENT_SECRET,
                                 scope=host_settings.SCOPE,
                                 user_agent=host_settings.USER_AGENT,
                                 message=MSG)



def fix_tasks_order(tasklists): # pylint:disable=too-many-locals
    """ Fix the order of tasks within the 'tasklists' list,
        as the tasks returned from the Google Tasks server are out of sequence.
        
        Reorders tasks in each tasklist so that subtasks appear under
        the respective parents, and in correct sibling order.
    """
    
    fn_name = "fix_tasks_order()"

    total_num_subtasks = 0
    total_num_tasks = 0
    num_tasklists = 0
    num_empty_tasklists = 0
    depth_counter = Counter()
    

    def process_task(tasks_sorted, tasks_grouped_by_parent_id, task, depth):
        """ Recursively process tasks and (optional) subtasks.
            Add task to 'tasks_sorted' list in order, and grouped by parent.
        """
        
        depth_counter[depth] += 1
        
        task[u'depth'] = depth
            
        tasks_sorted.append(task)
            
        # Process tasks for which this ID is the parent
        task_id = task.get('id', None)
        list_of_subtasks = tasks_grouped_by_parent_id.get(task_id, None)
        if list_of_subtasks:
            # Task has subtasks
            for subtask in list_of_subtasks:
                process_task(tasks_sorted, tasks_grouped_by_parent_id, subtask, 
                             depth + 1)


    for tasklist_dict in tasklists:
        num_tasklists += 1
        
        # tasklist_title = tasklist_dict['title']
        # logging.debug("%s: Fixing '%s'", fn_name, tasklist_title)
            
        if 'tasks' not in tasklist_dict:
            num_empty_tasklists += 1
            # logging.debug("%s: %s", fn_name, "Empty tasklist: No 'tasks' in tasklist")
            continue
            
        tasks_unsorted = tasklist_dict['tasks']
            
        # -----------------------------------
        # Process all the tasks in a tasklist
        # -----------------------------------
        
        # tasks_unsorted contains tasks in "random" order:
        #   subtasks may appear in the list before the subtask's parent task
        
        # ------------------------
        # Group tasks by parent ID
        # ------------------------
        # Root tasks will have '' parent
        tasks_grouped_by_parent_id = {} # New tasklist, so start with an empty dict
        # all_tasks_by_id = {}
        for task_dict in tasks_unsorted:
            total_num_tasks += 1
            parent_id = task_dict.get('parent', '') # Will be '' for root tasks
            if parent_id:
                # This is a subtask
                total_num_subtasks += 1
            if parent_id not in tasks_grouped_by_parent_id:
                # Creat a new list for 'parent_id'
                tasks_grouped_by_parent_id[parent_id] = []
            # Add this task to list of sibling tasks (keyed by parent_id)
            tasks_grouped_by_parent_id[parent_id].append(task_dict)
        
        # --------------------------------------
        # Sort each group of tasks by 'position'
        # --------------------------------------
        #   String indicating the position of the task among its sibling tasks 
        #   under the same parent task or at the top level. 
        #   If this string is greater than another task's corresponding position 
        #   string according to lexicographical ordering, the task is positioned 
        #   after the other task under the same parent task (or at the top level).    
        # Each group contains all the siblings below a given parent (or root)
        for parent_id, list_of_tasks_dicts in tasks_grouped_by_parent_id.iteritems():
            # Sort all the siblings in 'list_of_tasks' by 'position'
            list_of_tasks_dicts.sort(key=operator.itemgetter('position'))
            
        # -------------
        # Create a new sorted list of tasks
        # -------------
        tasks_sorted = []

        # Start by processing all root tasks
        # If a root task has children, process_task() will be called recursively to process the subtasks
        root_tasks_list = tasks_grouped_by_parent_id['']
        for root_task in root_tasks_list:
            process_task(tasks_sorted, tasks_grouped_by_parent_id, root_task, 
                         depth=0)
            
        tasklist_dict['tasks'] = tasks_sorted

    logging.info("%s: %s", fn_name,
        "Processed {:,} tasks in {:,} tasklists".format(
            total_num_tasks,
            num_tasklists))
    if num_empty_tasklists:
        logging.info("%s: There were %d empty tasklists", fn_name, num_empty_tasklists)
    logging.info("%s: %s", fn_name, 
        "There were {:,} sub-tasks ({:.2%})".format(
            total_num_subtasks, 
            total_num_subtasks * 1.0 / total_num_tasks))

    num_tasks_greater_than_depth1 = 0
    for depth, count in sorted(depth_counter.iteritems()):
        if depth > 1:
            num_tasks_greater_than_depth1 += count
        
        logging.info("%s: %s", fn_name,
            "    Depth {}: {:>6,}  {:>7.2%}".format(
            depth, 
            count,
            count * 1.0 / total_num_tasks))
        
    if num_tasks_greater_than_depth1:
        logging.info("%s: %s", fn_name,
            "    {:,} sub-tasks have depth greater than 1. That is;".format(
                num_tasks_greater_than_depth1))
            
        logging.info("%s: %s", fn_name,
            "          {:.2%} of all sub-tasks".format(
                num_tasks_greater_than_depth1 * 1.0 / total_num_subtasks))
            
        logging.info("%s: %s", fn_name,
            "          {:.2%} of all tasks".format(
                num_tasks_greater_than_depth1 * 1.0 / total_num_tasks))


                            
    
class WelcomeHandler(webapp2.RequestHandler): # pylint: disable=too-few-public-methods
    """ Displays an introductory web page, explaining what the app does and providing link to authorise.
    
        This page can be viewed even if the user is not logged in.
    """

    # Do not add auth_decorator to Welcome page handler, because we want anyone to be able to view the welcome page
    def get(self):
        """ Handles GET requests for settings.WELCOME_PAGE_URL """

        fn_name = "WelcomeHandler.get(): "

        logging.debug(fn_name + "<Start> (app version %s)" %appversion.version )
        logservice.flush()
        
        try:
            display_link_to_production_server = False # pylint: disable=invalid-name
            if not self.request.host in settings.PRODUCTION_SERVERS and settings.DISPLAY_LINK_TO_PRODUCTION_SERVER:
                logging.debug(fn_name + "Running on limited-access server '" + unicode(self.request.host) + 
                    "', displaying link to production server")
                logservice.flush()
                display_link_to_production_server = True # pylint: disable=invalid-name
            
            user = users.get_current_user()
            user_email = None
            is_admin_user = False
            if user:
                user_email = user.email()
                
                if not self.request.host in settings.PRODUCTION_SERVERS:
                    # logging.debug(fn_name + "DEBUG: Running on limited-access server")
                    if shared.is_test_user(user_email):
                        # Allow test user to see normal page content
                        logging.debug(fn_name + "TEST: Allow test user [" + unicode(user_email) + "] to see normal page content")
                        logservice.flush()
                        display_link_to_production_server = False # pylint: disable=invalid-name
                
                logging.debug(fn_name + "User is logged in, so displaying username and logout link")
                is_admin_user = users.is_current_user_admin()
            else:
                logging.debug(fn_name + "User is not logged in, so won't display logout link")
            logservice.flush()
                    
                    
            template_values = {'app_title' : host_settings.APP_TITLE,
                               'display_link_to_production_server' : display_link_to_production_server,
                               'production_server' : settings.PRODUCTION_SERVERS[0],
                               'host_msg' : host_settings.HOST_MSG,
                               'url_home_page' : settings.MAIN_PAGE_URL,
                               'product_name' : host_settings.PRODUCT_NAME,
                               'is_admin_user' : is_admin_user,
                               'user_email' : user_email,
                               'url_main_page' : settings.MAIN_PAGE_URL,
                               'msg': self.request.get('msg'),
                               'logout_url': users.create_logout_url(settings.WELCOME_PAGE_URL),
                               'url_discussion_group' : settings.url_discussion_group,
                               'email_discussion_group' : settings.email_discussion_group,
                               'url_issues_page' : settings.url_issues_page,
                               'url_source_code' : settings.url_source_code,
                               'app_version' : appversion.version,
                               'upload_timestamp' : appversion.upload_timestamp}
                               
            path = os.path.join(os.path.dirname(__file__), constants.PATH_TO_TEMPLATES, "welcome.html")
            self.response.out.write(template.render(path, template_values))
            logging.debug(fn_name + "<End>" )
            logservice.flush()
            
        except Exception, e: # pylint: disable=broad-except,invalid-name
            logging.exception(fn_name + "Caught top-level exception")
            shared.serve_outer_exception_message(self, e)
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()
    


class MainHandler(webapp2.RequestHandler):
    """Handler for /."""

    @auth_decorator.oauth_required
    def get(self):
        """ Main page, once user has been authenticated """

        fn_name = "MainHandler.get(): "

        logging.debug(fn_name + "<Start> (app version %s)" %appversion.version )
        logservice.flush()
        
        try:
            user = users.get_current_user()
            
            user_email = user.email()
            is_admin_user = users.is_current_user_admin()
            
            display_link_to_production_server = False # pylint: disable=invalid-name
            if not self.request.host in settings.PRODUCTION_SERVERS:
                logging.debug(fn_name + "Running on limited-access server: " + unicode(self.request.host))
                logservice.flush()
                if settings.DISPLAY_LINK_TO_PRODUCTION_SERVER:
                    display_link_to_production_server = True # pylint: disable=invalid-name
                if shared.is_test_user(user_email):
                    # Allow test user to see normal page
                    display_link_to_production_server = False # pylint: disable=invalid-name
                    logging.info(fn_name + "Allowing test user [" + unicode(user_email) + "] on limited access server")
                    logservice.flush()
                else:
                    logging.info(fn_name + "Rejecting non-test user [" + unicode(user_email) + "] on limited access server")
                    logservice.flush()
                    shared.reject_non_test_user(self)
                    logging.debug(fn_name + "<End> (Non test user on limited access server)")
                    logservice.flush()
                    return
                
            logging.debug(fn_name + "User = " + user_email)
            logservice.flush()                
            
            template_values = {'app_title' : host_settings.APP_TITLE,
                               'display_link_to_production_server' : display_link_to_production_server,
                               'production_server' : settings.PRODUCTION_SERVERS[0],
                               'host_msg' : host_settings.HOST_MSG,
                               'url_home_page' : settings.MAIN_PAGE_URL,
                               'product_name' : host_settings.PRODUCT_NAME,
                               'is_admin_user' : is_admin_user,
                               'user_email' : user_email,
                               'start_backup_url' : settings.START_BACKUP_URL,
                               'msg': self.request.get('msg'),
                               'logout_url': users.create_logout_url(settings.WELCOME_PAGE_URL),
                               'url_discussion_group' : settings.url_discussion_group,
                               'email_discussion_group' : settings.email_discussion_group,
                               'url_issues_page' : settings.url_issues_page,
                               'url_source_code' : settings.url_source_code,
                               'app_version' : appversion.version,
                               'upload_timestamp' : appversion.upload_timestamp}
                               
            path = os.path.join(os.path.dirname(__file__), constants.PATH_TO_TEMPLATES, "main.html")
            self.response.out.write(template.render(path, template_values))
            logging.debug(fn_name + "<End>" )
            logservice.flush()
        except Exception, e: # pylint: disable=broad-except,invalid-name
            logging.exception(fn_name + "Caught top-level exception")
            shared.serve_outer_exception_message(self, e)
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()
    
       

class StartBackupHandler(webapp2.RequestHandler):
    """ Handler to start the backup process. """
    
    @auth_decorator.oauth_required
    def get(self):
        """ Handles redirect from authorisation, or user accessing /startbackup directly
        
            The user will land on the GET handler if they go direct to /startbackup
            In that case, there should be no backup job record, or that job will not 
            have status of TO_BE_STARTED, so we silently redirect user to /main
            so that they can choose the backup opgtions and start a backup job
        
            The user may also be redirected here after auth_decorator authenticated a user in the post() method,
            because the post-authorisation redirection lands on the GET, not the POST. In that case,
            there should be a backup job record, and its status should be TO_BE_STARTED, so we call
            _start_backup() from here to start the export.
            
        """
        
        fn_name = "StartBackupHandler.get(): "
        
        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        try:
            user = users.get_current_user()
            user_email = user.email()
            
            is_test_user = shared.is_test_user(user_email)
            if not self.request.host in settings.PRODUCTION_SERVERS:
                # logging.debug(fn_name + "Running on limited-access server")
                if not is_test_user:
                    logging.info(fn_name + "Rejecting non-test user [" + str(user_email) + "] on limited access server")
                    logservice.flush()
                    shared.reject_non_test_user(self)
                    logging.debug(fn_name + "<End> (restricted access)" )
                    logservice.flush()
                    return
            
            # Retrieve the export job record for this user
            tasks_backup_job = model.ProcessTasksJob.get_by_key_name(user_email)
            
            # There should be a backup job record, and its status should be TO_BE_STARTED
            if tasks_backup_job is None:
                # If no DB record (e.g., first time user), redirect to /main
                logging.warning(fn_name + "No DB record for " + user_email + " so redirecting to " + 
                    settings.MAIN_PAGE_URL)
                logging.debug(fn_name + "<End> (No DB record)")
                logservice.flush()
                self.redirect(settings.MAIN_PAGE_URL)
                return
            
                # logging.warning(fn_name + "No DB record for " + user_email)
                # shared.serve_message_page(self, "No export job found. Please start a backup from the main menu.",
                    # "If you believe this to be an error, please report this at the link below",
                    # show_custom_button=True, custom_button_text='Go to main menu')
                # logging.warning(fn_name + "<End> No DB record")
                # logservice.flush()
                # return
            
            # This should be a new backup request, created in the POST handler, 
            # and the job status should be TO_BE_STARTED
            if tasks_backup_job.status != constants.ExportJobStatus.TO_BE_STARTED:
                # Check when job status was last updated. If it was less than settings.MAX_JOB_PROGRESS_INTERVAL
                # seconds ago, assume that another instance is already running,
                # log warning and redirect to progress page
                time_since_last_update = datetime.datetime.now() - tasks_backup_job.job_progress_timestamp
                if time_since_last_update.seconds < settings.MAX_JOB_PROGRESS_INTERVAL:
                    logging.info(fn_name + 
                        "User attempted to start backup whilst another job is already running for " + str(user_email))
                    logging.info(fn_name + "Previous job requested at " + str(tasks_backup_job.job_created_timestamp) + 
                        " is still running.")
                    logging.info(fn_name + "Previous worker started at " + str(tasks_backup_job.job_start_timestamp) + 
                        " and last job progress update was " + str(time_since_last_update.seconds) + 
                        " seconds ago, with status " +
                        str(tasks_backup_job.status))
                    # shared.serve_message_page(self, 
                        # "An existing backup is already running. Please wait for that backup to finish before starting a new backup.",
                        # "If you believe this to be an error, please report this at the link below",
                        # show_custom_button=True, 
                        # custom_button_text='Check backup progress', 
                        # custom_button_url=urljoin("https://" + self.request.host, settings.PROGRESS_URL))
                    logging.info(fn_name + "Redirecting to " + settings.PROGRESS_URL)
                    self.redirect(settings.PROGRESS_URL)
                        
                    logging.info(fn_name + "<End> (Backup already running)")
                    logservice.flush()
                    return
                    
                else:
                    # A previous job hasn't completed, and hasn't updated progress for more than 
                    # settings.MAX_JOB_PROGRESS_INTERVAL seconds, so assume that previous worker
                    # for this job has died, so log an error and start a new backup job.
                    logging.error(fn_name + "It appears that a previous job requested by " + str(user_email) + 
                        " at " + str(tasks_backup_job.job_created_timestamp) + " has stalled.")
                    logging.info(fn_name + "Previous worker started at " + str(tasks_backup_job.job_start_timestamp) + " and last job progress update was " + str(time_since_last_update.seconds) + " seconds ago." )
                    logging.info(fn_name + "Starting a new backup job")
                    logservice.flush()
                
            self._start_backup(tasks_backup_job)
            
        except Exception, e: # pylint: disable=broad-except,invalid-name
            logging.exception(fn_name + "Caught top-level exception")
            shared.serve_outer_exception_message(self, e)
            logging.error(fn_name + "<End> due to exception" )
            logservice.flush()

        logging.debug(fn_name + "<End>")
        logservice.flush()
            
        
    @auth_decorator.oauth_required
    def post(self): # pylint:disable=too-many-statements
        """ Handles POST request to settings.START_BACKUP_URL, which starts the backup process. """
        
        fn_name = "StartBackupHandler.post(): "
       
        logging.debug(fn_name + "<Start>")
        logservice.flush()

        try:
            user = users.get_current_user()
            user_email = user.email()

            is_test_user = shared.is_test_user(user_email)
            if not self.request.host in settings.PRODUCTION_SERVERS:
                # logging.debug(fn_name + "Running on limited-access server")
                if not is_test_user:
                    logging.info(fn_name + "Rejecting non-test user [" + str(user_email) + "] on limited access server")
                    logservice.flush()
                    shared.reject_non_test_user(self)
                    logging.debug(fn_name + "<End> (restricted access)" )
                    logservice.flush()
                    return
            
            # Retrieve the export job record for this user
            tasks_backup_job = model.ProcessTasksJob.get_by_key_name(user_email)
            
            if tasks_backup_job:
                logging.debug(fn_name + "DEBUG: Found job record for " + user_email + 
                    " with status = " + tasks_backup_job.status)
            
                # Check if there is a backup job in progress
                if not tasks_backup_job.status in constants.ExportJobStatus.STOPPED_VALUES:
                    logging.debug(fn_name + "DEBUG: Found in-progress job for " + user_email) 
                    # Check when job status was last updated. If it was less than settings.MAX_JOB_PROGRESS_INTERVAL
                    # seconds ago, assume that another instance is already running, 
                    # log warning and redirect to progress page
                    time_since_last_update = datetime.datetime.now() - tasks_backup_job.job_progress_timestamp
                    if time_since_last_update.seconds < settings.MAX_JOB_PROGRESS_INTERVAL:
                        logging.warning(fn_name + 
                            "User attempted to start backup whilst another job is already running for " + str(user_email))
                        logging.info(fn_name + "Previous job requested at " + 
                            str(tasks_backup_job.job_created_timestamp) + " is still running.")
                        logging.info(fn_name + "Previous worker started at " + 
                            str(tasks_backup_job.job_start_timestamp) + " and last job progress update was " + 
                            str(time_since_last_update.seconds) + " seconds ago, with status " +
                            str(tasks_backup_job.status))
                        logging.info(fn_name + "Redirecting to " + settings.PROGRESS_URL)
                        self.redirect(settings.PROGRESS_URL)
                        logging.info(fn_name + "<End> (Backup already running)")
                        logservice.flush()
                        return
                        
                    else:
                        # A previous job hasn't completed, and hasn't updated progress for more than 
                        # settings.MAX_JOB_PROGRESS_INTERVAL seconds, so assume that previous worker
                        # for this job has died, so log an error and start a new backup job.
                        logging.error(fn_name + "It appears that a previous job requested by " + str(user_email) + 
                            " at " + str(tasks_backup_job.job_created_timestamp) + " has stalled.")
                        logging.info(fn_name + "Previous worker started at " + str(tasks_backup_job.job_start_timestamp) + " and last job progress update was " + str(time_since_last_update.seconds) + " seconds ago." )
                        logging.info(fn_name + "Starting a new backup job")
                        logservice.flush()
                    
            # ===================================
            #   Create new backup job for user
            # ===================================
            logging.debug(fn_name + "Storing job details for " + str(user_email))
      
            # Create a DB record, using the user's email address as the key
            tasks_backup_job = model.ProcessTasksJob(key_name=user_email)
            tasks_backup_job.user = user
            tasks_backup_job.job_type = 'export'
            tasks_backup_job.include_completed = (self.request.get('include_completed') == 'True')
            tasks_backup_job.include_deleted = (self.request.get('include_deleted') == 'True')
            tasks_backup_job.include_hidden = (self.request.get('include_hidden') == 'True')
            tasks_backup_job.job_created_timestamp = datetime.datetime.now()
            tasks_backup_job.put()

            logging.debug(fn_name + "include_hidden = " + str(tasks_backup_job.include_hidden) +
                                    ", include_completed = " + str(tasks_backup_job.include_completed) +
                                    ", include_deleted = " + str(tasks_backup_job.include_deleted))
            logservice.flush()
            
            self._start_backup(tasks_backup_job)
                
            logging.debug(fn_name + "<End>")
            logservice.flush()
            
        except Exception, e: # pylint: disable=broad-except,invalid-name
            logging.exception(fn_name + "Caught top-level exception")
            shared.serve_outer_exception_message(self, e)
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()

            
    @auth_decorator.oauth_required        
    def _start_backup(self, tasks_backup_job): # pylint: disable=too-many-statements
        """Place the backup job request on the taskqueue.
        
           The worker will retrieve the job details from the DB record.
        """
    
        fn_name = "StartBackupHandler._start_backup(): "
        logging.debug(fn_name + "<Start>")
        logservice.flush()
    
        try:
            user = users.get_current_user()
            user_email = user.email()                
            
            tasks_backup_job.job_start_timestamp = datetime.datetime.now()
            tasks_backup_job.put()
            
            # Add the request to the tasks queue, passing in the user's email so that the task can access the
            # database record
            tq_q = taskqueue.Queue(settings.PROCESS_TASKS_REQUEST_QUEUE_NAME)
            tq_t = taskqueue.Task(url=settings.WORKER_URL, params={settings.TASKS_QUEUE_KEY_NAME : user_email}, method='POST')
            logging.debug(fn_name + "Adding task to " + str(settings.PROCESS_TASKS_REQUEST_QUEUE_NAME) + 
                " queue, for " + str(user_email))
            logservice.flush()
            
            retry_count = settings.NUM_API_TRIES
            while retry_count > 0:
                retry_count = retry_count - 1
                try:
                    tq_q.add(tq_t)
                    break
                    
                except Exception, e: # pylint: disable=broad-except,invalid-name
                    tasks_backup_job.job_progress_timestamp = datetime.datetime.now()
                    tasks_backup_job.message = 'Waiting for server ...'
                    
                    if retry_count > 0:
                        
                        logging.warning(fn_name + "Exception adding job to taskqueue, " +
                            str(retry_count) + " attempts remaining: "  + shared.get_exception_msg(e))
                        logservice.flush()
                        
                        # Give taskqueue some time before trying again
                        if retry_count <= 2:
                            sleep_time = settings.FRONTEND_API_RETRY_SLEEP_DURATION
                        else:
                            sleep_time = 1
                        
                        logging.info(fn_name + "Sleeping for " + str(sleep_time) + 
                            " seconds before retrying")
                        logservice.flush()
                        # Update job_progress_timestamp so that job doesn't time out
                        tasks_backup_job.job_progress_timestamp = datetime.datetime.now()
                        tasks_backup_job.put()
                        
                        time.sleep(sleep_time)
                        
                    else:
                        logging.exception(fn_name + "Exception adding job to taskqueue")
                        logservice.flush()
                
                        tasks_backup_job.status = constants.ExportJobStatus.ERROR
                        tasks_backup_job.message = ''
                        tasks_backup_job.error_message = "Error starting export process: " + \
                            shared.get_exception_msg(e)
                        
                        logging.debug(fn_name + "Job status: '" + str(tasks_backup_job.status) + ", progress: " + 
                            str(tasks_backup_job.total_progress) + ", msg: '" + 
                            str(tasks_backup_job.message) + "', err msg: '" + str(tasks_backup_job.error_message))
                        logservice.flush()
                        tasks_backup_job.put()
                        
                        shared.serve_message_page(self, "Error creating tasks export job.",
                            "Please report the following error using the link below",
                            shared.get_exception_msg(e),
                            show_custom_button=True, custom_button_text="Return to main menu")
                        
                        logging.debug(fn_name + "<End> (error adding job to taskqueue)")
                        logservice.flush()
                        return
                    

            logging.debug(fn_name + "Redirecting to " + settings.PROGRESS_URL)
            logservice.flush()
            self.redirect(settings.PROGRESS_URL)
            
            logging.debug(fn_name + "<end>")
            logservice.flush()
    
        except Exception, e: # pylint: disable=broad-except,invalid-name
            logging.exception(fn_name + "Caught top-level exception")
            shared.serve_outer_exception_message(self, e)
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()
    
    
    
class ShowProgressHandler(webapp2.RequestHandler):
    """Handler to display progress to the user """
    
    @auth_decorator.oauth_required
    def get(self): # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        """Display the progress page, which includes a refresh meta-tag to recall this page every n seconds"""
        
        fn_name = "ShowProgressHandler.get(): "
    
        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        try:
            user = users.get_current_user()
                
            user_email = user.email()

            display_link_to_production_server = False # pylint: disable=invalid-name
            if not self.request.host in settings.PRODUCTION_SERVERS:
                # logging.debug(fn_name + "Running on limited-access server")
                if settings.DISPLAY_LINK_TO_PRODUCTION_SERVER:
                    display_link_to_production_server = True # pylint: disable=invalid-name
                if shared.is_test_user(user_email):
                    # Allow test user to see normal page
                    display_link_to_production_server = False # pylint: disable=invalid-name
                else:
                    logging.info(fn_name + "Rejecting non-test user [" + str(user_email) + "] on limited access server")
                    logservice.flush()
                    shared.reject_non_test_user(self)
                    logging.debug(fn_name + "<End> (Non test user on limited access server)")
                    logservice.flush()
                    return
            
            show_log_option = (user_email in settings.SHOW_LOG_OPTION_USERS)
            # DEBUG:
            # logging.debug(fn_name + "show_log_option = " + str(show_log_option))
            # logging.debug(fn_name + "user_email = " + user_email)
            # logging.debug(settings.SHOW_LOG_OPTION_USERS)
            # logservice.flush()

            status = None
            error_message = None
            progress = 0
            job_start_timestamp = None
            job_execution_time = None
            include_completed = False
            include_deleted = False
            include_hidden = False
            job_msg = ''
            
            # Retrieve the DB record for this user
            tasks_backup_job = model.ProcessTasksJob.get_by_key_name(user_email)
            if tasks_backup_job is None:
                # If no DB record (e.g., first time user), redirect to /main
                logging.warning(fn_name + "No DB record for " + user_email + " so redirecting to " + 
                    settings.WELCOME_PAGE_URL)
                logging.debug(fn_name + "<End> (No DB record)")
                logservice.flush()
                self.redirect(settings.WELCOME_PAGE_URL)
                return
            else:            
                # total_progress is only updated once all the tasks have been retrieved in a single tasklist.
                # tasklist_progress is updated every settings.TASK_COUNT_UPDATE_INTERVAL seconds within the retrieval process
                # for each tasklist. This ensures progress updates happen at least every
                # settings.TASK_COUNT_UPDATE_INTERVAL seconds,
                # which wouldn't happen if it takes a long time to retrieve a large number of tasks in a single tasklist.
                # So, the current progress = total_progress + tasklist_progress
                status = tasks_backup_job.status
                error_message = tasks_backup_job.error_message
                progress = tasks_backup_job.total_progress + tasks_backup_job.tasklist_progress
                job_start_timestamp = tasks_backup_job.job_start_timestamp
                if job_start_timestamp:
                    job_execution_time = datetime.datetime.now() - job_start_timestamp
                else:
                    job_execution_time = None
                time_since_job_was_requested = datetime.datetime.now() - tasks_backup_job.job_created_timestamp
                include_completed = tasks_backup_job.include_completed
                include_deleted = tasks_backup_job.include_deleted
                include_hidden = tasks_backup_job.include_hidden
                job_msg = tasks_backup_job.message

                # -----------------------------------
                #   Check job status and progress
                # -----------------------------------
                
                if status == constants.ExportJobStatus.TO_BE_STARTED:
                    logging.debug(fn_name + "Waiting for worker to start. Job was requested " +
                        str(time_since_job_was_requested.seconds) + " seconds ago at " +
                        str(tasks_backup_job.job_created_timestamp))
                    # Check if job has been started within settings.MAX_TIME_ALLOWED_FOR_JOB_TO_START 
                    # If job hasn't started yet by then, log error and display msg to user
                    if time_since_job_was_requested.seconds > settings.MAX_TIME_ALLOWED_FOR_JOB_TO_START:
                        # Job hasn't started withing maximum allowed time
                        logging.error(fn_name + "Backup has not started within maximum allowed " + 
                            str(settings.MAX_TIME_ALLOWED_FOR_JOB_TO_START) + " seconds")
                        # -------------------------------------------------------------
                        #   Display message to user and don't display progress page
                        # -------------------------------------------------------------
                        shared.serve_message_page(self, 
                            "Backup was not started within maximum startup time. Please try running your backup again.",
                            error_message,
                            "If you believe this to be an error, or if this has happened before, please report this at the issues link below",
                            show_custom_button=True, custom_button_text='Go to main menu')
                            
                        logging.warning(fn_name + "<End> (Job didn't start)")
                        logservice.flush()
                        return
                        
                elif not status in constants.ExportJobStatus.STOPPED_VALUES:
                    # Check if the job has updated progress within the maximum progress update time.
                    time_since_last_update = datetime.datetime.now() - tasks_backup_job.job_progress_timestamp
                    if time_since_last_update.seconds > settings.MAX_JOB_PROGRESS_INTERVAL:
                        # Job status has not been updated recently, so consider job to have stalled.
                        logging.error(fn_name + "Job created at " + str(tasks_backup_job.job_created_timestamp) + " appears to have stalled. Status was " + tasks_backup_job.status + ", progress = " + str(progress))
                        logging.error(fn_name + "Last job progress update was " + str(time_since_last_update.seconds) +
                            " seconds ago.")
                            
                        if job_execution_time:
                            logging.info(fn_name + "Job was started by worker " + str(job_execution_time.seconds) + 
                                " seconds ago at " + str(job_start_timestamp) + " UTC")
                        else:
                            logging.error(fn_name + "Job has not been started yet by worker")
                        logservice.flush()
                        
                        if tasks_backup_job.error_message:
                            error_message = tasks_backup_job.error_message + " - Status was " + tasks_backup_job.status + ", progress = " + str(progress)
                        else:
                            error_message = "Status was " + tasks_backup_job.status + ", progress = " + str(progress)
                        # -------------------------------------------------------------
                        #   Display message to user and don't display progress page
                        # -------------------------------------------------------------
                        shared.serve_message_page(self, 
                            "Retrieval of tasks appears to have stalled. Please try running your backup again.",
                            error_message,
                            "If you believe this to be an error, or if this has happened before, please report this at the issues link below",
                            show_custom_button=True, custom_button_text='Go to main menu')
                            
                        logging.warning(fn_name + "<End> (Job stalled)")
                        logservice.flush()
                        return
            
            if status == constants.ExportJobStatus.EXPORT_COMPLETED:
                logging.info(fn_name + "Retrieved " + str(progress) + " tasks for " + str(user_email))
            elif status == constants.ExportJobStatus.TO_BE_STARTED:
                # Job hasn't been started yet, so no progress or job start time
                logging.debug(fn_name + "Backup for " + str(user_email) + ", requested at " + str(tasks_backup_job.job_created_timestamp) + " UTC, hasn't started yet.")
            else:
                logging.debug(fn_name + "Status = " + str(status) + ", progress = " + str(progress) + 
                    " for " + str(user_email) + ", worker started at " + str(job_start_timestamp) + " UTC")
            
            if error_message:
                logging.warning(fn_name + "Error message: " + str(error_message))
            if job_msg:
                logging.debug(fn_name + "Job msg: " + str(job_msg))
                
            logservice.flush()
            
            path = os.path.join(os.path.dirname(__file__), constants.PATH_TO_TEMPLATES, "progress.html")
            
            template_values = {'app_title' : host_settings.APP_TITLE,
                               'display_link_to_production_server' : display_link_to_production_server,
                               'production_server' : settings.PRODUCTION_SERVERS[0],
                               'host_msg' : host_settings.HOST_MSG,
                               'url_home_page' : settings.MAIN_PAGE_URL,
                               'product_name' : host_settings.PRODUCT_NAME,
                               'status' : status,
                               'progress' : progress,
                               'include_completed' : include_completed,
                               'include_deleted' : include_deleted,
                               'include_hidden' : include_hidden,
                               'job_msg' : job_msg,
                               'error_message' : error_message,
                               'job_start_timestamp' : job_start_timestamp,
                               'refresh_interval' : settings.PROGRESS_PAGE_REFRESH_INTERVAL,
                               'large_list_html_warning_limit' : settings.LARGE_LIST_HTML_WARNING_LIMIT,
                               'user_email' : user_email,
                               'display_technical_options' : shared.is_test_user(user_email),
                               'url_main_page' : settings.MAIN_PAGE_URL,
                               'results_url' : settings.RESULTS_URL,
                               'show_log_option' : show_log_option,
                               'msg': self.request.get('msg'),
                               'logout_url': users.create_logout_url(settings.WELCOME_PAGE_URL),
                               'url_discussion_group' : settings.url_discussion_group,
                               'email_discussion_group' : settings.email_discussion_group,
                               'url_issues_page' : settings.url_issues_page,
                               'url_source_code' : settings.url_source_code,
                               'app_version' : appversion.version,
                               'upload_timestamp' : appversion.upload_timestamp}
            self.response.out.write(template.render(path, template_values))
            logging.debug(fn_name + "<End>")
            logservice.flush()
            
        except Exception, e: # pylint: disable=broad-except,invalid-name
            logging.exception(fn_name + "Caught top-level exception")
            shared.serve_outer_exception_message(self, e)
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()
        

        
class ReturnResultsHandler(webapp2.RequestHandler):
    """Handler to return results to user in the requested format """
        
    @auth_decorator.oauth_required
    def get(self):
        """ If user attempts to go direct to /results, they come in a a GET request, 
            so we redirect to /progress so user can choose format.
        
            The user may also be redirected here after auth_decorator authenticated a user in the post() method,
            because the post-authorisation redirection lands on the GET, not the POST
            
            If we are here due to re-authentication, the web page uses JavaScript to action the user's original selection
        """
        fn_name = "ReturnResultsHandler.get(): "
        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        try:
            logging.info(fn_name + "Expected POST for " + 
                str(settings.RESULTS_URL) + 
                "; May have been user going direct to URL, or re-authentication when user selected an action, so redirecting to " + 
                str(settings.PROGRESS_URL))
            logservice.flush()
            # Display the progress page to allow user to choose format for results
            self.redirect(settings.PROGRESS_URL)
            logging.debug(fn_name + "<End>")
            logservice.flush()
        except Exception, e: # pylint: disable=broad-except,invalid-name
            logging.exception(fn_name + "Caught top-level exception")
            shared.serve_outer_exception_message(self, e)
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()
    
    
    @auth_decorator.oauth_required
    def post(self): # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        """ Return results to the user, in format chosen by user """
        fn_name = "ReturnResultsHandler.post(): "
        
        logging.debug(fn_name + "<Start>")
        logservice.flush()

        # try:
            # headers = self.request.headers
            # for k,v in headers.items():
                # logging.debug(fn_name + "browser header: " + str(k) + " = " + str(v))
                
            # logging.debug(fn_name + "Cookies ==>")
            # logging.debug(self.request.cookies)
            # logservice.flush()
                
        # except Exception, e: # pylint: disable=broad-except,invalid-name
            # logging.exception(fn_name + "Exception retrieving request headers")
            # logservice.flush()
            
      
        try: # pylint: disable=too-many-nested-blocks
            user = users.get_current_user()
            
            user_email = user.email()
            
            
            display_link_to_production_server = False # pylint: disable=invalid-name
            if not self.request.host in settings.PRODUCTION_SERVERS:
                # logging.debug(fn_name + "Running on limited-access server")
                if settings.DISPLAY_LINK_TO_PRODUCTION_SERVER:
                    display_link_to_production_server = True # pylint: disable=invalid-name
                if shared.is_test_user(user_email):
                    # Allow test user to see normal page
                    display_link_to_production_server = False # pylint: disable=invalid-name
                else:
                    logging.info(fn_name + "Rejecting non-test user [" + str(user_email) + "] on limited access server")
                    logservice.flush()
                    shared.reject_non_test_user(self)
                    logging.debug(fn_name + "<End> (Non test user on limited access server)")
                    logservice.flush()
                    return
            
            
            # Performing the user's action, so delete the cookie (set negative age)
            shared.delete_cookie(self.response, 'actionId')
            
            # Retrieve the DB record for this user
            tasks_backup_job = model.ProcessTasksJob.get_by_key_name(user_email)
                
            if tasks_backup_job is None:
                # If no DB record (e.g., first time user), redirect to /main
                logging.error(fn_name + "No tasks_backup_job record for " + user_email + 
                    " so redirecting to " + settings.WELCOME_PAGE_URL)
                logging.debug(fn_name + "<End> (No DB record)")
                logservice.flush()
                self.redirect(settings.WELCOME_PAGE_URL)
                return
                
            else:            
                include_completed = tasks_backup_job.include_completed
                include_deleted = tasks_backup_job.include_deleted
                include_hidden = tasks_backup_job.include_hidden
                total_progress = tasks_backup_job.total_progress
                
            # Retrieve the data DB record(s) for this user
            #logging.debug(fn_name + "Retrieving details for " + str(user_email))
            #logservice.flush()
            
            tasklists_records = db.GqlQuery("SELECT * "
                                            "FROM TasklistsData "
                                            "WHERE ANCESTOR IS :1 "
                                            "ORDER BY idx ASC",
                                            db.Key.from_path(settings.DB_KEY_TASKS_BACKUP_DATA, user_email))

            num_records = tasklists_records.count()
            
            if num_records is None:
                # There should be at least one record, since we will only execute this function if ProcessTasksJob.status == completed
                # Possibly user got here by doing a POST without starting a backup request first 
                # (e.g. page refresh from an old job)
                logging.error(fn_name + "No data records found for " + str(user_email))
                
                # TODO: Display better error to user &/or redirect to allow user to start a backup job
                logging.debug(fn_name + "<End> due to no data for this user")
                logservice.flush()
                
                # TODO: Display better error page. Perhaps _serve_retry_page ????
                self.response.set_status(412, "No data for this user. Please retry backup request.")
                return
            
            rebuilt_pkl = ""
            for tasklists_record in tasklists_records:
                #logging.debug("Reassembling blob number " + str(tasklists_record.idx))
                rebuilt_pkl = rebuilt_pkl + tasklists_record.pickled_tasks_data
                
            logging.debug(fn_name + "Reassembled " + str(len(rebuilt_pkl)) + " bytes from " + str(num_records) + " blobs")
            logservice.flush()
            
            tasklists = pickle.loads(rebuilt_pkl)
            rebuilt_pkl = None # Not needed, so release it
            
            # ==========================================================
            # Fix the order of tasks, and add 'depth' value to each task
            # ==========================================================
            # Reorder tasks in each tasklist so that subtasks appear under
            # the respective parents, and in correct sibling order
            fix_tasks_order(tasklists)
            
              
            # User selected format to export as
            # Note: If format == 'html_raw', we will display the web page rather than return a file (or send email)
            export_format = self.request.get("export_format")
            
            # We pass the job_start_timestamp from the Progress page so that we can display it on the HTML page
            job_start_timestamp = self.request.get('job_start_timestamp')
            
            # User selected HTML display options (used when format == html)
            display_completed_tasks = (self.request.get('display_completed_tasks') == 'True')
            dim_completed_tasks = (self.request.get('dim_completed_tasks') == 'True')
            display_completed_date_field = (self.request.get('display_completed_date_field') == 'True')
            display_due_date_field = (self.request.get('display_due_date_field') == 'True')
            display_updated_date_field = (self.request.get('display_updated_date_field') == 'True')
            display_invalid_tasks = (self.request.get('display_invalid_tasks') == 'True')
            display_hidden_tasks = (self.request.get('display_hidden_tasks') == 'True')
            display_deleted_tasks = (self.request.get('display_deleted_tasks') == 'True')
            due_selection = self.request.get('due_selection')
            
            export_using_localtime = (self.request.get('export_using_localtime') == 'True')
            export_offset_hours_str = self.request.get('export_offset_hours')
            display_using_localtime = (self.request.get('display_using_localtime') == 'True')
            display_offset_hours_str = self.request.get('display_offset_hours')
            
            logging.info(fn_name + "Selected export format = " + str(export_format))
            logservice.flush()
            
            if export_format == 'html_raw':
                # Use the settings in the Display form
                use_localtime_offset = display_using_localtime
                offset_hours_str = display_offset_hours_str
            else:
                # Use the settings in the Export form
                use_localtime_offset = export_using_localtime
                offset_hours_str = export_offset_hours_str
            
            logging.debug(fn_name + "DEBUG: Local time adjustment options:" + 
                "\n    export_using_localtime     = " + str(export_using_localtime) +
                "\n    export_offset_hours_str    = " + str(export_offset_hours_str) +
                "\n    display_using_localtime    = " + str(display_using_localtime) +
                "\n    display_offset_hours_str   = " + str(display_offset_hours_str) +
                "\n    use_localtime_offset       = " + str(use_localtime_offset))
            logservice.flush()
            
            adjust_timestamps = False
            offset_hours = 0.0
            
            # The user can choose to adjust ther server's UTC time to their local time
            # Do not adjust times for formats which expect UTC;
            #   ICS specifically uses Zulu time
            #   Import/Export CSV and GTBack are designed to be re-imported into Google Tasks, which expects UTC
            #   The raw formats, by definition, should be raw ????
            if use_localtime_offset:
                try:
                    # The number of (decimal) hours to add to the 'completed' and 'updated' datetime values,
                    # to convert from server time (UTC) to the user's local time
                    offset_hours = float(offset_hours_str)
                    logging.info(fn_name + "User has chosen " + str(offset_hours) + 
                        " hours offset for localtime")
                    logservice.flush()
                    adjust_timestamps = True
                except Exception, e: # pylint: disable=broad-except,invalid-name
                    # Should never happen, because the value is set by <option> values on the HTML form 
                    logging.error(fn_name + "Error converting offset hours form value [" +
                        str(offset_hours_str) + "] to a float value, so using zero offset: " + shared.get_exception_msg(e))
                    logservice.flush()
                    offset_hours = 0.0
            else:
                # Return the date/time as set by the Google Tasks server
                offset_hours = 0.0
                
                        
            logging.debug(fn_name + "Display options:" + 
                "\n    completed               = " + str(display_completed_tasks) +
                "\n    hidden                  = " + str(display_hidden_tasks) +
                "\n    deleted                 = " + str(display_deleted_tasks) +
                "\n    invalid                 = " + str(display_invalid_tasks))
            logging.debug(fn_name + "Local time adjustment options:" + 
                "\n    adjust_timestamps       = " + str(adjust_timestamps) +
                "\n    offset_hours            = " + str(offset_hours))
            logservice.flush()
            
            if due_selection in ['due_now', 'overdue']:
                # If user selected to display due or overdue tasks, use this value to determine which tasks to display.
                # Using value from user's browser, since that will be in user's current timezone. Server doesn't know user's current timesone.
                # logging.debug(fn_name + "User chose to only display tasks due, where due_year = " + str(self.request.get('due_year')) +
                                # ", due_month = " + str(self.request.get('due_month')) +
                                # ", due_day = " + str(self.request.get('due_day')))
                try:
                    due_date_limit = datetime.date(int(self.request.get('due_year')),
                                                int(self.request.get('due_month')), 
                                                int(self.request.get('due_day'))) 
                except Exception, e: # pylint: disable=broad-except,invalid-name
                    due_date_limit = datetime.date(datetime.MINYEAR,1,1)
                    logging.exception(fn_name + "Error interpretting due date limit from browser. Using " + str(due_date_limit))
                    logservice.flush()
            else:
                due_date_limit = None
            if export_format == 'html_raw':
                logging.debug(fn_name + "due_selection = '" + str(due_selection) + "', due_date_limit = " + str(due_date_limit) )
                logservice.flush()
            
            num_completed_tasks = 0
            num_incomplete_tasks = 0
            num_display_tasks = 0
            num_invalid_tasks_to_display = 0
            num_hidden_tasks_to_display = 0
            num_deleted_tasks_to_display = 0
            num_not_displayed = 0
            total_num_invalid_tasks = 0
            total_num_orphaned_hidden_or_deleted_tasks = 0
            
            # logging.debug(fn_name + "DEBUG: tasklists ==>")
            # logging.debug(tasklists)
            # logservice.flush()
            # ---------------------------------------------------------------------------------------------
            #    Add/modify elements for html_raw if required)
            # ---------------------------------------------------------------------------------------------
            for tasklist in tasklists:
                # if shared.is_test_user(user_email) and settings.DUMP_DATA:
                    # # DEBUG
                    # logging.debug(fn_name + "TEST: tasklist ==>")
                    # logging.debug(tasklist)
                    # logservice.flush()
                
                # If there are no tasks in a tasklist, Google returns a dictionary containing just 'title'
                # In that case, worker.py doesn't add a 'tasks' element in the tasklist dictionary
                # if there are no tasks for a tasklist.
                
                tasks = tasklist.get(u'tasks')
                if not tasks:
                    # No tasks in tasklist
                    if shared.is_test_user(user_email):
                        logging.debug(fn_name + "TEST: Empty tasklist: '" + str(tasklist.get(u'title')) + "'")
                        logservice.flush()
                    continue
                
                num_tasks = len(tasks)
                if num_tasks > 0: # Non-empty tasklist
                    task_idx = 0
                    
                    while task_idx < num_tasks:
                        task = tasks[task_idx]
                        
                        if adjust_timestamps:
                            # Adjust timestamps to reflect local time instead of server's UTC
                            # Note that this only adjusts export types that do NOT use UTC
                            #   e.g. 'outlook' will be adjusted, but 'ics' will not
                            updated_time = task.get(u'updated')
                            if updated_time:
                                task[u'updated'] = updated_time + datetime.timedelta(hours=offset_hours)
                            completed_time = task.get(u'completed')
                            if completed_time:
                                task[u'completed'] = completed_time + datetime.timedelta(hours=offset_hours)
                        
                        task_idx = task_idx + 1   
                        
                        
                        
                        # TODO: Ensure that all text is correctly tabbed according to depth
                        # if export_format == 'tabbed_text':
                        #     tabs = '\t'*depth
                        #     task[u'tabs'] = tabs
                        #     if task.has_key(u'notes') and task[u'notes']:
                        #         notes_lines = task[u'notes'].split('\n')
                        #         notes = ''
                        #         line_end = ''
                        #         for note_line in notes_lines:
                        #             notes += line_end + tabs + note_line
                        #             line_end = '\n'
                        #         
                        #         
                        #         
                        #         
                        #         
                        #         
                        #         notes_lines = notes.split()
                        #         notes = ''
                        #         for note_line in notes_lines:
                        #             notes += tabs + note_line + '\n'
                        #         task[u'notes'] = notes
                        

                    # Add extra properties for HTML view;
                    #    Add 'indent' property for HTML pages so that tasks can be correctly indented
                    #    Determine if task should be displayed, based on user selections
                    if export_format == 'html_raw':
                        #logging.debug(fn_name + "Setting metadata for " + export_format + " format")
                        #logservice.flush()
                        tasklist_has_tasks_to_display = False
                        for task in tasks:
                            display = True # Display by default
                            
                            # Determine if task should be displayed
                            if not display_completed_tasks and task[u'status'] == 'completed':
                                # User chose not to display completed tasks
                                display = False
                                num_not_displayed = num_not_displayed + 1
                            elif not display_hidden_tasks and task.get(u'hidden'):
                                display = False
                            elif not display_deleted_tasks and task.get(u'deleted'):
                                display = False
                            else:
                                if due_selection == "all":
                                    # Ignore 'due' property
                                    display = True
                                    tasklist_has_tasks_to_display = True
                                else:
                                    display = False
                                    try:
                                        if task.has_key(u'due'):
                                            if due_selection == "any_due":
                                                # Display task if it has a 'due' property (ignore value)
                                                display = True
                                                tasklist_has_tasks_to_display = True
                                            elif due_selection == "due_now" and task[u'due'] <= due_date_limit:
                                                # Display task if it is due on or before selected due date (e.g. today)
                                                display = True
                                                tasklist_has_tasks_to_display = True
                                            elif due_selection == "overdue" and task[u'due'] < due_date_limit:
                                                # Display only if task is due before selected due date (e.g. today)
                                                display = True
                                                tasklist_has_tasks_to_display = True
                                        else:
                                            if due_selection == "none":
                                                # Display only if task is does not have a due date
                                                display = True
                                                tasklist_has_tasks_to_display = True
                                    except Exception, e: # pylint: disable=broad-except,invalid-name
                                        logging.exception(fn_name + "Exception determining if task is due")
                                        # DEBUG:
                                        logging.debug(fn_name + "Task ==>")
                                        logging.debug(task)
                                        logservice.flush()
                            
                            task['display'] = display
                                
                            if display:
                                # Get some stats to display to user
                                num_display_tasks = num_display_tasks + 1
                                if task.get('status') == 'completed':
                                    num_completed_tasks = num_completed_tasks + 1
                                else:
                                    num_incomplete_tasks = num_incomplete_tasks + 1
                                if task.get(u'depth', 0) < 0:
                                    task[u'invalid'] = True
                                    num_invalid_tasks_to_display = num_invalid_tasks_to_display + 1
                                    # logging.debug(fn_name + "Found invalid task ==>")
                                    # logging.debug(task)
                                    # logservice.flush()
                                if task.get(u'hidden'):
                                    num_hidden_tasks_to_display = num_hidden_tasks_to_display + 1
                                if task.get(u'deleted'):
                                    num_deleted_tasks_to_display = num_deleted_tasks_to_display + 1
                                    
                            try:
                                depth = int(task[u'depth'])
                            except KeyError, e:
                                logging.exception(fn_name + "Missing depth for " + task[u'id'] + ", " + task[u'title'])
                                logservice.flush()
                                task[u'depth'] = -2
                                depth = 0
                            if depth < 0:
                                depth = 0
                            # Set number of pixels to indent task by, as a string,
                            # to use in style="padding-left:nnn" in HTML pages
                            task[u'indent'] = str(depth * settings.TASK_INDENT).strip()
                            
                            # Delete unused properties to reduce memory usage, to improve the likelihood of being able to 
                            # successfully render very big tasklists
                            #     Unused properties: kind, id, etag, selfLink, parent, position, depth
                            # 'kind', 'id', 'etag' are not used or displayed
                            # 'parent' is no longer needed, because we now use the indent property to display task/sub-task relationships
                            # 'position' is not needed because we rely on the fact that tasks are returned in position order
                            # 'depth' is no longer needed, because we use indent to determine how far in to render the task
                            if task.has_key(u'kind'):
                                del(task[u'kind'])
                            if task.has_key(u'id'):
                                del(task[u'id'])
                            if task.has_key(u'etag'):
                                del(task[u'etag'])
                            if task.has_key(u'selfLink'):
                                del(task[u'selfLink'])
                            if task.has_key(u'parent'):
                                del(task[u'parent'])
                            if task.has_key(u'position'):
                                del(task[u'position'])
                            if task.has_key(u'depth'):
                                del(task[u'depth'])

                        if tasklist_has_tasks_to_display:
                            tasklist[u'tasklist_has_tasks_to_display'] = True
            
            logservice.flush()
            logging.debug(fn_name + "Number of tasks = " + str(total_progress))
            logging.debug(fn_name + "    total_num_orphaned_hidden_or_deleted_tasks = " + 
                str(total_num_orphaned_hidden_or_deleted_tasks))
            logging.debug(fn_name + "    total_num_invalid_tasks = " + str(total_num_invalid_tasks))
            logging.debug(fn_name + "    num_not_displayed = " + str(num_not_displayed))
            logservice.flush()
            
            # If user hasn't chosen to use a localtime offset, the datetime prefix will be 'UTC '
            # Otherwise the prefix an empty string
            if adjust_timestamps:
                # Don't include the UTC prefix if the user has chosen a different offset
                utc_prefix_str = ""
                utc_suffix_str = ""
            else:
                #Default prefix, used to indicate that we are exporting/displaying server time, which is UTC
                utc_prefix_str = "UTC "
                utc_suffix_str = " UTC"
            
            template_values = {'app_title' : host_settings.APP_TITLE,
                               'display_link_to_production_server' : display_link_to_production_server,
                               'production_server' : settings.PRODUCTION_SERVERS[0],
                               'host_msg' : host_settings.HOST_MSG,
                               'product_name' : host_settings.PRODUCT_NAME,
                               'tasklists': tasklists,
                               'include_completed' : include_completed, # Chosen at start of backup
                               'include_deleted' : include_deleted, # Chosen at start of backup
                               'include_hidden' : include_hidden, # Chosen at start of backup
                               'utc_prefix_str' : utc_prefix_str,
                               'utc_suffix_str' : utc_suffix_str,
                               'total_progress' : total_progress,
                               'num_display_tasks' : num_display_tasks,
                               'num_completed_tasks' : num_completed_tasks,
                               'num_incomplete_tasks' : num_incomplete_tasks,
                               'num_invalid_tasks_to_display' : num_invalid_tasks_to_display,
                               'num_hidden_tasks_to_display' : num_hidden_tasks_to_display,
                               'num_deleted_tasks_to_display' : num_deleted_tasks_to_display,
                               'display_completed_tasks' : display_completed_tasks, # Chosen at progress page
                               'dim_completed_tasks' : dim_completed_tasks, # Chosen at progress page
                               'due_selection' : due_selection, # Chosen at progress page
                               'due_date_limit' : str(due_date_limit), # Chosen at progress page
                               'display_invalid_tasks' : display_invalid_tasks, # Chosen at progress page
                               'display_completed_date_field' : display_completed_date_field, # Chosen at progress page
                               'display_due_date_field' : display_due_date_field, # Chosen at progress page
                               'display_updated_date_field' : display_updated_date_field, # Chosen at progress page
                               'user_email' : user_email, 
                               'now' : datetime.datetime.now(),
                               'job_start_timestamp' : job_start_timestamp,
                               'exportformat' : export_format,
                               'logout_url': users.create_logout_url(settings.WELCOME_PAGE_URL),
                               'url_main_page' : settings.MAIN_PAGE_URL,
                               'url_home_page' : settings.WELCOME_PAGE_URL,
                               'url_discussion_group' : settings.url_discussion_group,
                               'email_discussion_group' : settings.email_discussion_group,
                               'url_issues_page' : settings.url_issues_page,
                               'url_source_code' : settings.url_source_code,
                               'app_version' : appversion.version,
                               'upload_timestamp' : appversion.upload_timestamp}
            
            # Filename format is "tasks_FORMAT_EMAILADDR_YYYY-MM-DD.EXT"
            # CAUTION: Do not include characters that may not be valid on some filesystems (e.g., colon is not valid on Windows)
            output_filename_base = "tasks_%s_%s_%s" % (export_format, user_email, datetime.datetime.now().strftime("%Y-%m-%d"))
     
            # template file name format "tasks_template_FORMAT.EXT",
            #   where FORMAT = export_format (e.g., 'outlook')
            #     and EXT = the file type extension (e.g., 'csv')
            if export_format == 'ics':
                self._write_ics_using_template(template_values, export_format, output_filename_base)
            elif export_format in ['outlook', 'raw', 'raw1', 'raw2', 'log', 'import_export']:
                self._write_csv_using_template(template_values, export_format, output_filename_base)
            elif export_format == 'html_raw':
                self._write_html_raw(template_values)
            elif export_format == 'RTM':
                self._send_email_using_template(template_values, export_format, user_email, output_filename_base)
            elif export_format == 'py':
                self._write_text_using_template(template_values, export_format, output_filename_base, 'py')
            elif export_format in ['tabbed_text', 'spaced_text']:
                self._write_text_using_template(template_values, export_format, output_filename_base, 'txt')
            elif export_format == 'gtb':
                self._write_gtbak_format(tasklists, export_format, output_filename_base)
            else:
                logging.warning(fn_name + "Unsupported export format: %s" % export_format)
                # TODO: Handle invalid export_format nicely - display message to user & go back to main page
                self.response.out.write("<br /><h2>Unsupported export format: %s</h2>" % export_format)
            tasklists = None
            #logging.debug(fn_name + "Calling garbage collection")
            gc.collect()
            logging.debug(fn_name + "<End>")
            logservice.flush()
        except Exception, e: # pylint: disable=broad-except,invalid-name
            logging.exception(fn_name + "Caught top-level exception")
            
            self.response.headers["Content-Type"] = "text/html; charset=utf-8"
            try:
                # Clear "Content-Disposition" so user will see error in browser.
                # If not removed, output goes to file (if error generated after "Content-Disposition" was set),
                # and user would not see the error message!
                if self.response.headers and "Content-Disposition" in self.response.headers:
                    del self.response.headers["Content-Disposition"]
            except Exception, ie: # pylint: disable=broad-except,invalid-name
                logging.debug(fn_name + "Error deleting 'Content-Disposition' from headers: " + shared.get_exception_msg(ie))
            self.response.clear() 
            shared.serve_outer_exception_message(self, e)
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()

        
    def _send_email_using_template(self, template_values, export_format, user_email, output_filename_base): # pylint: disable=too-many-locals,too-many-statements
        """ Send an email, formatted according to the specified .txt template file
            Currently supports export_format = 'RTM' (Remember The Milk)
        """
        # Potential TODO items (if email quota is sufficient)
        #   TODO: Allow other formats
        #   TODO: Allow attachments (e.g. Outlook CSV) ???
        #   TODO: Improve subject line
        fn_name = "_send_email_using_template(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        # if shared.is_test_user(user_email):
          # logging.debug(fn_name + "TEST: Creating email body using template")
        # Use a template to convert all the tasks to the desired format 
        template_filename = "tasks_template_%s.txt" % export_format
        
        path = os.path.join(os.path.dirname(__file__), constants.PATH_TO_TEMPLATES, template_filename)
        email_body = template.render(path, template_values)
        
        sender=user_email

        # sender = "zzzz@logic-a-to-b.com"
        # logging.debug(fn_name + "DEBUG: Sending using invalid email address " + sender)
        # logservice.flush()

        # if shared.is_test_user(user_email):
          # logging.debug(fn_name + "TEST: Sending email")
        # TODO: Catch exception sending & display to user ??
        # According to "C:\Program Files\Google\google_appengine\google\appengine\api\mail.py", 
        #   end_mail() doesn't return any value, but can throw InvalidEmailError when invalid email address provided
        send_try_count = 0
        MAX_SEND_TRY_COUNT = 2 # pylint: disable=invalid-name
        while send_try_count < MAX_SEND_TRY_COUNT:
            msg1 = None
            msg2 = None
            send_try_count += 1
            
            try:
                mail.send_mail(sender=sender,
                               to=user_email,
                               subject=output_filename_base,
                               body=email_body)
                               
                if shared.is_test_user(user_email):
                    logging.debug(fn_name + "TEST: Email sent to %s" % user_email)
                else:
                    logging.debug(fn_name + "Email sent")
                  
                shared.serve_message_page(self, "Email sent to " + str(user_email), 
                    show_back_button=True, back_button_text="Continue", show_heading_messages=False)
                
                break
                               
            except apiproxy_errors.OverQuotaError:
                # Refer to https://developers.google.com/appengine/docs/quotas#When_a_Resource_is_Depleted
                logging.exception(fn_name + "Unable to send email")
                msg1 = "Sorry, unable to send email due to quota limitations"
                msg2 = "It may be that your email is too large, or that too many emails have been sent by others in the past 24 hours."
                shared.serve_message_page(self, msg1, msg2,
                    show_custom_button=True, 
                    custom_button_text='Return to menu', 
                    custom_button_url = settings.RESULTS_URL,
                    show_heading_messages=True,
                    template_file="message.html")    
                logging.debug(fn_name + "<End> (due to OverQuotaError)")
                logservice.flush()
                return
                
            except mail_errors.InvalidSenderError, e: # pylint: disable=invalid-name
                if send_try_count < MAX_SEND_TRY_COUNT:
                    logging.warning(fn_name + "Unable to send email from " + unicode(sender))
                    sender = host_settings.APP_TITLE + "@" + get_application_id() + ".appspotmail.com"
                    logging.debug(fn_name + "Will retry sending from " + unicode(sender))
                    logservice.flush()
                else:
                    logging.exception(fn_name + "Unable to send email")
                    logservice.flush()
                    msg1 = "Sorry, unable to send email"
                    msg2 = shared.get_exception_msg(e)
            
            except Exception, e: # pylint: disable=broad-except,invalid-name
                if send_try_count < MAX_SEND_TRY_COUNT:
                    logging.warning(fn_name + "Unable to send email from " + unicode(sender) +
                        " Will try again ... [" + shared.get_exception_msg(e) + "]")
                    logservice.flush()
                else:
                    logging.exception(fn_name + "Unable to send email")
                    logservice.flush()
                    msg1 = "Sorry, unable to send email"
                    msg2 = shared.get_exception_msg(e)
                
            if send_try_count >= MAX_SEND_TRY_COUNT:
                shared.serve_message_page(self, msg1, msg2,
                    show_custom_button=True, 
                    custom_button_text='Return to menu', 
                    custom_button_url = settings.RESULTS_URL,
                    show_heading_messages=True,
                    template_file="message.html")    
                logging.debug(fn_name + "<End> (due to exception)")
                logservice.flush()
                return
                
                
        logging.debug(fn_name + "<End>")
        logservice.flush()


    def _write_ics_using_template(self, template_values, export_format, output_filename_base):
        """ Write an ICS file according to the specified .ics template file
            Currently supports export_format = 'ics'
        """
        fn_name = "_write_ics_using_template(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        template_filename = "tasks_template_%s.ics" % export_format
        output_filename = shared.convert_unicode_to_str(output_filename_base + ".ics")
        self.response.headers["Content-Type"] = "text/calendar"
        self.response.headers.add_header(
            "Content-Disposition", "attachment; filename=%s" % output_filename)

        path = os.path.join(os.path.dirname(__file__), constants.PATH_TO_TEMPLATES, template_filename)
        if shared.is_test_user(template_values['user_email']):
            logging.debug(fn_name + "TEST: Writing %s format to %s" % (export_format, output_filename))
        else:
            logging.debug(fn_name + "Writing %s format" % export_format)
        self.response.out.write(template.render(path, template_values))
        logging.debug(fn_name + "<End>")
        logservice.flush()
        

    def _write_csv_using_template(self, template_values, export_format, output_filename_base):
        """ Write a CSV file according to the specified .csv template file
            Currently supports export_format = 'outlook', 'raw', 'raw1', 'raw2' and 'import_export'
        """
        fn_name = "_write_csv_using_template(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        template_filename = "tasks_template_%s.csv" % export_format
        
        output_filename = shared.convert_unicode_to_str(output_filename_base + ".csv")
        self.response.headers["Content-Type"] = "text/csv"
        self.response.headers.add_header(
            "Content-Disposition", "attachment; filename=%s" % output_filename)

        
        path = os.path.join(os.path.dirname(__file__), constants.PATH_TO_TEMPLATES, template_filename)
        if shared.is_test_user(template_values['user_email']):
            logging.debug(fn_name + "TEST: Writing %s format to %s" % (export_format, output_filename))
        else:
            logging.debug(fn_name + "Writing %s format" % export_format)
        self.response.out.write(template.render(path, template_values))
        logging.debug(fn_name + "<End>")
        logservice.flush()


    def _write_text_using_template(self, template_values, export_format, output_filename_base, file_extension):
        """ Write a TXT file according to the specified .txt template file
            Currently supports export_format = 'py', 'tabbed_text', 'spaced_text' 
        """
        fn_name = "_write_text_using_template(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        template_filename = "tasks_template_%s.%s" % (export_format, file_extension)
        output_filename = shared.convert_unicode_to_str(output_filename_base + "." + file_extension)
        self.response.headers["Content-Type"] = "text/plain"
        self.response.headers.add_header(
            "Content-Disposition", "attachment;filename=%s" % output_filename)

        
        path = os.path.join(os.path.dirname(__file__), constants.PATH_TO_TEMPLATES, template_filename)
        if shared.is_test_user(template_values['user_email']):
            logging.debug(fn_name + "TEST: Writing %s format to %s" % (export_format, output_filename))
        else:
            logging.debug(fn_name + "Writing %s format" % export_format)
        # TODO: Output in a manner suitable for downloading from an Android phone
        #       Currently sends source of HTML page as output_filename
        #       Perhaps try Content-Type = "application/octet-stream" ???
        self.response.out.write(template.render(path, template_values))
        logging.debug(fn_name + "<End>")
        logservice.flush()

        
    def _write_gtbak_format(self, tasklists, export_format, output_filename_base):
        fn_name = "_write_gtbak_format(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        logging.debug(fn_name + "Building GTBak structure")
        
        gtback_list = []
        for tasklist in tasklists:
            tasklist_name = tasklist[u'title']
            tasks = tasklist.get(u'tasks')
            if not tasks:
                # Empty tasklist
                continue
            for task in tasks:
                gtb_task = {}
                # We create a new Task, which contains text fields formatted such that they can be processed by the same
                # code that parses CSV files in import-tasks
                # Fields supported in gtb_task;
                #   "tasklist_name","title","notes","status","due","completed","deleted","hidden",depth
                #       'due' and 'completed' are datetime object in tasklists, and must be converted to text
                #       'deleted' and 'hidden' are Python boolean object, and must be converted to text
                #       Other fields are passed through unchanged
                
                # Mandatory fields; "tasklist_name","title","status",depth
                gtb_task[u'tasklist_name'] = tasklist_name
                gtb_task[u'title'] = task.get(u'title')
                gtb_task[u'status'] = task.get(u'status')
                gtb_task[u'depth'] = task.get(u'depth')
                
                
                # Optional fields; "notes","due","completed","deleted","hidden"
                # Write date/time fields in same format as used by import_export CSV
                notes = task.get(u'notes')
                if notes:
                    gtb_task[u'notes'] = notes
                                       
                if u'due' in task:
                    # If it exists, the 'due' element is a date object 
                    #    (if original 'due' element was >= '0001-01-01'),
                    # or None 
                    #    (if original 'due' element was '0000-01-01')
                    # import-tasks requires a string, so use format_datetime_as_str() to convert object to string
                    gtb_task[u'due'] = shared.format_datetime_as_str(task[u'due'], 
                        "%Y-%m-%d", prefix="UTC ", date_only=True)
                
                if u'completed' in task:
                    # If it exists, the 'completed' element is a datetime object 
                    #    (if original 'completed' element was >= '0001-01-01 00:00:00'),
                    # or None 
                    #    (if original 'completed' element was '0000-01-01 00:00:00')
                    # import-tasks requires a string, so use format_datetime_as_str() to convert object to string
                    gtb_task[u'completed'] = shared.format_datetime_as_str(task[u'completed'],
                        "%Y-%m-%d %H:%M:%S", prefix="UTC ")
                    
                deleted = task.get(u'deleted')
                if deleted:
                    gtb_task[u'deleted'] = 'True' # import-tasks requires a string
                hidden = task.get(u'hidden')
                if hidden:
                    gtb_task[u'hidden'] = 'True' # import-tasks requires a string
                    
                # Add the task to the list of tasks to be exported
                gtback_list.append(gtb_task)
        self._write_raw_file(pickle.dumps(gtback_list), export_format, output_filename_base, 
            'GTBak', "application/octet-stream", pickle.dumps('v1.0'))
        
        logging.debug(fn_name + "<End>")
        logservice.flush()

        
    def _write_raw_file(self, file_content, export_format, output_filename_base, file_extension, content_type="text/plain", content_prefix=None): # pylint: disable=too-many-arguments
        """ Write file_content to a file.
        
            file_content            Contents to be written to file
            export_format           Name of the format, used for logging
            output_filename_base    The filename (minus the extension)
            file_extension          The file extension. Should match the type of data in file_content
            content_type            Used in the "Content-Type" to indicate the file type to the browser
                                    Possibly useful values for Content-Type;  "text/plain" or "application/octet-stream"
            content_prefix          [Optional] Content to be written to file BEFORE file_content
                                    e.g. When content is pickled, prefix can be a pickled interface version identifier

        """
        fn_name = "_write_raw_file(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        output_filename = shared.convert_unicode_to_str(output_filename_base + "." + file_extension)
        self.response.headers["Content-Type"] = content_type
        self.response.headers.add_header(
            "Content-Disposition", "attachment;filename=%s" % output_filename)
        logging.debug(fn_name + "Writing " + str(export_format) + " format file")
        if content_prefix:
            self.response.out.write(content_prefix)
        self.response.out.write(file_content)
        logging.debug(fn_name + "<End>")
        logservice.flush()

        
    def _write_html_raw(self, template_values): # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        """ Manually build an HTML representation of the user's tasks.
        
            This method creates the page manually, which uses significantly less memory than using Django templates.
            It is also faster, but does not support multi-line notes. Notes are displayed on a single line.
        """
        
        fn_name = "_write_html_raw() "
        
        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        # User ID
        user_email = template_values.get('user_email')
        
        # The actual tasklists and tasks to be displayed
        tasklists = template_values.get('tasklists')
        
        # Stats
        total_progress = template_values.get('total_progress') # Total num tasks retrieved, calculated by worker
        num_display_tasks = template_values.get('num_display_tasks') # Number of tasks that will be displayed
        num_completed_tasks = template_values.get('num_completed_tasks') # Number of completed tasks that will be displayed
        num_incomplete_tasks = template_values.get('num_incomplete_tasks') # Number of incomplete tasks that will be displayed
        num_invalid_tasks_to_display = template_values.get('num_invalid_tasks_to_display') # Number of invalid tasks that will be displayed
        num_hidden_tasks_to_display = template_values.get('num_hidden_tasks_to_display') # Number of hidden tasks that will be displayed
        num_deleted_tasks_to_display = template_values.get('num_deleted_tasks_to_display') # Number of deleted tasks that will be displayed
        
        # Values chosen by user at start of backup
        include_completed = template_values.get('include_completed')
        include_hidden = template_values.get('include_hidden')
        include_deleted = template_values.get('include_deleted')
        
        # The utc_suffix_str is only set when the retrieved time is UTC. If the user selects a
        # non-zero offset, utc_suffix_str is empty.
        # Here, we use the UTC prefix (used in CSV file) as a suffix for 'updated' and 'completed'
        utc_suffix_str = template_values.get('utc_suffix_str') 
        
        # Values chosen by user at progress page, before displaying this page
        due_selection = template_values.get('due_selection')
        due_date_limit = template_values.get('due_date_limit')
        display_invalid_tasks = template_values.get('display_invalid_tasks')
        display_completed_tasks = template_values.get('display_completed_tasks')
        dim_completed_tasks = template_values.get('dim_completed_tasks')
        display_completed_date_field = template_values.get('display_completed_date_field')
        display_updated_date_field = template_values.get('display_updated_date_field')
        display_due_date_field = template_values.get('display_due_date_field')
        
        # Project info &/or common project values
        job_start_timestamp = template_values.get('job_start_timestamp')
        logout_url = template_values.get('logout_url')
        url_discussion_group = template_values.get('url_discussion_group')
        email_discussion_group = template_values.get('email_discussion_group')
        url_issues_page = template_values.get('url_issues_page')
        url_source_code = template_values.get('url_source_code')
        app_title = template_values.get('app_title')
        app_version = template_values.get('app_version')
        
        logging.debug(fn_name + "Writing HTML page")
        logservice.flush()
        
        # self.response.out.write("""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN">""")
        self.response.out.write("""<!doctype html>""")
        self.response.out.write("""<html> <head> <title>""")
        self.response.out.write(app_title)
        self.response.out.write(""" - List of tasks</title>
            <link rel="stylesheet" type="text/css" href="static/tasks_backup.css" />
            <link rel="stylesheet" type="text/css" href="static/print.css" media="print" />
            <script type="text/javascript">

              var _gaq = _gaq || [];
              _gaq.push(['_setAccount', 'UA-30118203-1']);
              _gaq.push(['_trackPageview']);

              (function() {
                var ga = document.createElement('script'); ga.type = 'text/javascript'; ga.async = true;
                ga.src = ('https:' == document.location.protocol ? 'https://ssl' : 'http://www') + '.google-analytics.com/ga.js';
                var s = document.getElementsByTagName('script')[0]; s.parentNode.insertBefore(ga, s);
              })();

            </script>
            </head>
            <body>""")
            
        # Put the TOP anchor for the first tasklist at the top of the page, so the user can see that they are at the top,
        # and also to ensure page heading and back button are visible.
        # Put subsequent TOP anchors above the BOTTOM anchor of the previous tasklist, so that
        # the "To top ..." link is visible when a user is traversing from bottom to top
        self.response.out.write("""<a name="tl1_top"> </a>""")
        self.response.out.write("""<div class="no-print usertitle">Authorised user: """)
    
        self.response.out.write(user_email)
        self.response.out.write(' <span class="logout-link">[ <a href="')
        self.response.out.write(logout_url)
        self.response.out.write('">Log out</a> ]</span></div>')
        
        self.response.out.write("""<div class="break">""") # Div to contain Back and Print buttons on same row. Don't print buttons.
        # self.response.out.write("""<div class="break no-print"><button onclick="javascript:history.back(-1)" class="back-button"  value="Back">Back</button></div>""")
        
        # Need to provide the specific URL of the progress page. We can't use history.back() because the user may have used 
        # the next/previous tasklist links one or more times.
        self.response.out.write("""<div class="no-print" style="float: left;"><button onclick="window.location.href = '%s'" class="back-button"  value="Back">Back</button></div>""" % settings.PROGRESS_URL)
        self.response.out.write("""<div class="no-print" style="float: right;"><button onclick="window.print()" class="back-button"  value="Print page">Print page</button></div>""")
        self.response.out.write("""<div style="clear: both;"></div>""")
        self.response.out.write("""</div>""") # Closing div to contain Back and Print buttons on same row
        
        num_tasklists = len(tasklists)
        if num_tasklists > 0:
            # Display the job timestamp, so that it is clear when the snapshot was taken
            self.response.out.write("""<div class="break"><h2>Tasks for """)
            self.response.out.write(user_email)
            self.response.out.write(""" as at """)
            self.response.out.write(job_start_timestamp)
            self.response.out.write(""" UTC</h2>""")
            if num_display_tasks == total_progress:
                self.response.out.write("""<div>Retrieved """ + str(num_tasklists) + """ task lists.</div>""")
            else:
                self.response.out.write("""<div>Retrieved """ + str(total_progress) + """ tasks from """ +
                    str(num_tasklists) + """ task lists.</div>""")
            
            self.response.out.write("""<div>Displaying """ + str(num_display_tasks))
            if due_selection == 'any_due':
                self.response.out.write(""" tasks with any due date""")
            elif due_selection == 'due_now':
                self.response.out.write(""" current tasks (due on or before """ + str(due_date_limit) + """)""")
            elif due_selection == 'overdue':
                self.response.out.write(""" overdue tasks (due before """ + str(due_date_limit) + """)""")
            else:
                # User chose "All tasks"
                self.response.out.write(""" tasks.""")
            self.response.out.write("""</div>""")
                
            if display_completed_tasks and include_completed and num_completed_tasks > 0:
                # User chose to retrieve complete tasks (start page) AND user chose to display completed tasks (progress page)
                self.response.out.write("""<div class="comment">""" + str(num_completed_tasks) + """ completed tasks</div>""")
            self.response.out.write("""<div class="comment">""" + str(num_incomplete_tasks) + """ incomplete (needsAction) tasks</div>""")
                
            if include_hidden and num_hidden_tasks_to_display > 0:
                # User chose to retrieve hidden tasks (start page)
                self.response.out.write("""<div class="comment">""" + str(num_hidden_tasks_to_display) + """ hidden tasks</div>""")
                    
            if include_deleted and num_deleted_tasks_to_display > 0:
                # User chose to retrieve deleted tasks (start page)
                self.response.out.write("""<div class="comment">""" + str(num_deleted_tasks_to_display) + """ deleted tasks</div>""")
                    
            if display_invalid_tasks and num_invalid_tasks_to_display > 0:
                # User chose to display invalid tasks (progress page)
                self.response.out.write("""<div class="comment">""" + str(num_invalid_tasks_to_display) + """ parentless, invalid or corrupted tasks</div>""")
            self.response.out.write("""</div>""")
            
            tl_num = 1
            for tasklist in tasklists:
                tasklist_title = tasklist.get(u'title')
                if not tasklist_title.strip():
                    tasklist_title = "<Unnamed Tasklist>"
                tasklist_title = shared.escape_html(tasklist_title)
                
                tasklist_has_tasks_to_display = tasklist.get('tasklist_has_tasks_to_display', False)

                tasks = tasklist.get(u'tasks')
                if tasks:
                    num_tasks = len(tasks)
                else:
                    num_tasks = 0
                    
                if num_tasklists > 1:
                    # If there is more than one tasklist, display Next link
                    self.response.out.write("""<div class="tasklist-link no-print"><a href="#tl%s_bottom">Next tasklist</a>&nbsp;&nbsp;&nbsp;&nbsp;<a href="#page_bottom">Bottom of page</a></div>""" % 
                        tl_num)
                    
                self.response.out.write("""<div class="tasklist"><div class="tasklistheading"><span class="tasklistname">""")
                self.response.out.write(tasklist_title)
                self.response.out.write("""</span> (""")
                self.response.out.write(str(num_tasks))
                self.response.out.write(""" tasks)</div>""")
                
                if num_tasks > 0 and tasklist_has_tasks_to_display:
                    self.response.out.write("""<div class="tasks">""")
                        
                    for task in tasks:
                        if not task.get(u'display', True):
                            # Skip tasks that don't match user's selection
                            continue
                    
                        task_title = task.get(u'title', "<No Task Title>")
                        if not task_title.strip():
                            task_title = "<Unnamed Task>"
                        task_title = shared.escape_html(task_title)
                        
                        task_notes = shared.escape_html(task.get(u'notes', None))
                        task_deleted = task.get(u'deleted', None)
                        task_hidden = task.get(u'hidden', None)
                        task_invalid = task.get(u'invalid', False)
                        task_indent = str(task.get('indent', 0))
                        
                        
                        if u'due' in task:
                            task_due = shared.format_datetime_as_str(task[u'due'], '%a, %d %b %Y')
                        else:
                            task_due = None
                            
                        if u'updated' in task:
                            task_updated = shared.format_datetime_as_str(task[u'updated'], 
                                '%H:%M:%S %a, %d %b %Y') + utc_suffix_str
                        else:
                            task_updated = None
                        
                        if task.get(u'status') == 'completed':
                            task_completed = True
                            task_status_str = "&#x2713;"
                        else:
                            task_completed = False
                            task_status_str = "[ &nbsp;]"
                            
                        if u'completed' in task:
                            # There is a 'completed' element in the Task dictionary object.
                            # Note that sometimes the original 'completed' RFC 3339 datetime string
                            # returned from the server is '0000-01-01T00:00:00.000Z', which is
                            # converted by the worker to '1900-01-01 00:00:00'
                            task_completed_date = shared.format_datetime_as_str(task[u'completed'], 
                                '%H:%M %a, %d %b %Y') + utc_suffix_str
                        else:
                            # There is no 'completed' element, so display an empty string
                            task_completed_date = ''
                        
                        dim_class = ""
                        if task_completed and dim_completed_tasks:
                            dim_class = "dim"
                        if task_deleted or task_hidden or task_invalid:
                            dim_class = "dim"
                        
                        self.response.out.write("""<div style="padding-left:""")
                        self.response.out.write(task_indent)
                        self.response.out.write("""px" class="task-html1 """)
                        self.response.out.write(dim_class)
                        # Note, additional double-quote (4 total), as the class= attribute is 
                        # terminated with a double-quote after the class name
                        self.response.out.write("""" ><div ><span class="status-cell">""")
                        self.response.out.write(task_status_str)
                        self.response.out.write("""</span><span class="task-title-html1">""")
                        self.response.out.write(task_title)
                        self.response.out.write("""</span></div><div class="task-details-html1">""")
                        
                        if task_completed and display_completed_date_field:
                            self.response.out.write("""<div class="task-attribute"><span class="fieldlabel">COMPLETED:</span> """)
                            self.response.out.write(task_completed_date)
                            self.response.out.write("""</div>""")
                                    
                        if task_notes:
                            self.response.out.write("""<div class="task-notes">""")
                            self.response.out.write(task_notes)
                            self.response.out.write("""</div>""")
                                    
                        if task_due and display_due_date_field:
                            self.response.out.write("""<div class="task-attribute"><span class="fieldlabel">Due: </span>""")
                            self.response.out.write(task_due)        
                            self.response.out.write("""</div>""")
                                    
                        if task_updated and display_updated_date_field:
                            self.response.out.write("""<div class="task-attribute"><span class="fieldlabel">Updated:</span> """)
                            self.response.out.write(task_updated)
                            self.response.out.write("""</div>""")
                            
                        if task_invalid:
                            self.response.out.write("""<div class="task-attribute-hidden-or-deleted">- Invalid -</div>""")
                                
                        if task_deleted:
                            self.response.out.write("""<div class="task-attribute-hidden-or-deleted">- Deleted -</div>""")
                                
                        if task_hidden:
                            self.response.out.write("""<div class="task-attribute-hidden-or-deleted">- Hidden -</div>""")
                        # End of task details div
                        # End of task div
                        self.response.out.write("""</div>
                            </div>""")
                            
                    # End of tasks div
                    self.response.out.write("""</div>""")
                    
                    # Put subsequent TOP anchor of the next tasklist above the BOTTOM anchor of this tasklist, so that
                    # the "To top ..." link is visible when a user is traversing from bottom to top
                    self.response.out.write("""<a name="tl%s_top"> </a>""" % (tl_num+1))
                        
                    self.response.out.write("""<a name="tl%s_bottom"> </a>""" % tl_num)
                    self.response.out.write("""<div class="tasklist-link no-print"><a href="#tl%s_top">To top of %s tasklist</a>&nbsp;&nbsp;&nbsp;<a href="#tl1_top">Top of page</a></div>""" % 
                        (tl_num, tasklist_title))
                    tl_num = tl_num + 1
                                           
                else:
                    self.response.out.write("""
                            <div class="no-tasks">
                                No tasks to display
                            </div>""")
                
                self.response.out.write("""<hr />""")
                
            self.response.out.write("""
                    <div class="break">
                        NOTE: Due, Updated and Completed dates and times are UTC, because that is how Google stores them.
                    </div>""")
                    
        else:
            self.response.out.write("""
                <div class="break">
                        <h3>No tasklists found for %s</h3>
                    </div>""" % user_email)

        self.response.out.write("""<a name="page_bottom"> </a>""")
        self.response.out.write("""
                <div class="break footer">
                    Produced by %(app_title)s, version %(app_version)s
                </div>
                <div class="project-footer">
                    <div class="break">
                        Questions or comments? Go to <a href="http://%(url_discussion_group)s">%(url_discussion_group)s</a>
                        or email <a href="mailto:%(email_discussion_group)s">%(email_discussion_group)s</a>
                    </div>
                    <div class="break">
                        Please report bugs or suggest improvements at <a href="http:/%(url_issues_page)s">%(url_issues_page)s</a>
                    </div>
                    <div class="break">
                        Source code for this project is at <a href="http://%(url_source_code)s">%(url_source_code)s</a>
                    </div>
                </div>""" %
                { 'url_discussion_group' : url_discussion_group,
                  'email_discussion_group' : email_discussion_group,
                  'url_issues_page' : url_issues_page,
                  'url_source_code' : url_source_code,
                  'app_title' : host_settings.APP_TITLE,
                  'app_version' : app_version }
            )

        self.response.out.write("""</body></html>""")
        tasklists = None
        gc.collect()
        logging.debug(fn_name + "<End>")
        logservice.flush()
               
    

class RobotsHandler(webapp2.RequestHandler):

    def get(self):
        """If not running on production server, return robots.txt with disallow all
           to prevent search engines indexing test servers.
        """
        # Return contents of robots.txt
        self.response.headers['Content-Type'] = "text/plain"
        self.response.out.write("User-agent: *\n")
        if self.request.host == settings.PRODUCTION_SERVERS[0]:
            # Only allow first (primary) server to be indexed
            logging.debug("Returning robots.txt with allow all")
            self.response.out.write("Disallow:\n")
        else:
            logging.debug("Returning robots.txt with disallow all")
            self.response.out.write("Disallow: /\n")
       

# def urlfetch_timeout_hook(service, call, request, response):
    # if call != 'Fetch':
        # return

    # # Make the default deadline 30 seconds instead of 5.
    # if not request.has_deadline():
        # request.set_deadline(30.0)
        
        
app = webapp2.WSGIApplication( # pylint: disable=invalid-name
    [
        ("/robots.txt",                             RobotsHandler),
        (settings.MAIN_PAGE_URL,                    MainHandler),
        (settings.WELCOME_PAGE_URL,                 WelcomeHandler),
        (settings.RESULTS_URL,                      ReturnResultsHandler),
        (settings.START_BACKUP_URL,                 StartBackupHandler),
        (settings.PROGRESS_URL,                     ShowProgressHandler),
        (auth_decorator.callback_path,              auth_decorator.callback_handler()),
    ], debug=False)

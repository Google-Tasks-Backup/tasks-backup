#!/usr/bin/python2.5
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

"""Main web application handler for Google Tasks Backup."""

# Orig __author__ = "dwightguth@google.com (Dwight Guth)"
__author__ = "julie.smith.1999@gmail.com (Julie Smith)"

from google.appengine.dist import use_library
use_library("django", "1.2")

import logging
import os
import pickle
import sys
import gc
import cgi
import time

from apiclient import discovery
from apiclient.oauth2client import appengine
from apiclient.oauth2client import client

from google.appengine.api import mail
from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp import util
from google.appengine.runtime import apiproxy_errors
from google.appengine.runtime import DeadlineExceededError
from google.appengine.api import urlfetch_errors
from google.appengine.api import logservice # To flush logs

# Import from error so that we can process HttpError
from apiclient import errors as apiclient_errors


logservice.AUTOFLUSH_EVERY_SECONDS = 5
logservice.AUTOFLUSH_EVERY_BYTES = None
logservice.AUTOFLUSH_EVERY_LINES = 5
logservice.AUTOFLUSH_ENABLED = True

import httplib2
import Cookie

import datetime
from datetime import timedelta
import csv

import model
import settings
import appversion # appversion.version is set before the upload process to keep the version number consistent
import shared # Code which is common between tasks-backup.py and worker.py
import constants

  
    
class MainHandler(webapp.RequestHandler):
    """Handler for /."""

    def get(self):
        """ Main page, once user has been authenticated """

        fn_name = "MainHandler.get(): "

        logging.debug(fn_name + "<Start> (app version %s)" %appversion.version )
        logservice.flush()
        
        try:
            client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.get_settings(self.request.host)

            ok, user, credentials, fail_msg, fail_reason = shared.get_credentials(self)
            if not ok:
                # User not logged in, or no or invalid credentials
                logging.info(fn_name + "Get credentials error: " + fail_msg)
                logservice.flush()
                # self.redirect(settings.WELCOME_PAGE_URL)
                shared.redirect_for_auth(self, user)
                return
                
            user_email = user.email()
            is_admin_user = users.is_current_user_admin()
            
            is_authorized = True
            # logging.debug(fn_name + "Resetting auth_count cookie to zero")
            # logservice.flush()
            
            if self.request.host in settings.LIMITED_ACCESS_SERVERS:
                logging.debug(fn_name + "Running on limited-access server")
                if not shared.isTestUser(user_email):
                    logging.info(fn_name + "Rejecting non-test user [" + str(user_email) + "] on limited access server")
                    self.response.out.write("<h2>This is a test server. Access is limited to test users.</h2>")
                    logging.debug(fn_name + "<End> (restricted access)" )
                    logservice.flush()
                    return
              
            template_values = {'app_title' : app_title,
                               'host_msg' : host_msg,
                               'url_home_page' : settings.MAIN_PAGE_URL,
                               'product_name' : product_name,
                               'is_authorized': is_authorized,
                               'is_admin_user' : is_admin_user,
                               'user_email' : user_email,
                               'start_backup_url' : settings.START_BACKUP_URL,
                               'msg': self.request.get('msg'),
                               'logout_url': users.create_logout_url(settings.WELCOME_PAGE_URL),
                               'url_discussion_group' : settings.url_discussion_group,
                               'email_discussion_group' : settings.email_discussion_group,
                               'url_issues_page' : settings.url_issues_page,
                               'url_source_code' : settings.url_source_code,
                               'logout_url': users.create_logout_url(settings.WELCOME_PAGE_URL),
                               'app_version' : appversion.version,
                               'upload_timestamp' : appversion.upload_timestamp}
                               
            path = os.path.join(os.path.dirname(__file__), constants.PATH_TO_TEMPLATES, "main.html")
            self.response.out.write(template.render(path, template_values))
            logging.debug(fn_name + "<End>" )
            logservice.flush()
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            shared.serve_outer_exception_message(self, e)
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()
    
    
    
class WelcomeHandler(webapp.RequestHandler):
    """ Displays an introductory web page, explaining what the app does and providing link to authorise.
    
        This page can be viewed even if the user is not logged in.
    """

    def get(self):
        """ Handles GET requests for settings.WELCOME_PAGE_URL """

        fn_name = "WelcomeHandler.get(): "

        logging.debug(fn_name + "<Start> (app version %s)" %appversion.version )
        logservice.flush()
        
        try:
            client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.get_settings(self.request.host)

            ok, user, credentials, fail_msg, fail_reason = shared.get_credentials(self)
            if not ok:
                is_authorized = False
            else:
                is_authorized = True
            
            user_email = None
            if user:
                user_email = user.email()
            
            template_values = {'app_title' : app_title,
                               'host_msg' : host_msg,
                               'url_home_page' : settings.MAIN_PAGE_URL,
                               'product_name' : product_name,
                               'is_authorized': is_authorized,
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
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            shared.serve_outer_exception_message(self, e)
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()
    

    
class StartBackupHandler(webapp.RequestHandler):
    """ Handler to start the backup process. """
    
    def get(self):
        """ Handles redirect from authorisation.
            The only time we should get here is if retrieving credentials failed in _start_backup(), 
            and we were redirected here after successfully authenticating.
        
            There should be a backup job record, and its status should be STARTING

            shared.redirect_for_auth() stores the URL for the StartBackupHandler(), so when OAuthCallbackHandler()
            redirects to here (on successful authorisation), it comes in as a GET, so we call _start_backup() to 
            (re)start the export.
        """
        
        fn_name = "StartBackupHandler.get(): "
        
        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        try:
            # Only get the user here. The credentials are retrieved within _start_backup()
            # Don't need to check if user is logged in, because all pages (except '/') are set as secure in app.yaml
            user = users.get_current_user()
            user_email = user.email()
            # Retrieve the export job record for this user
            tasks_backup_job = model.ProcessTasksJob.get_by_key_name(user_email)
            
            # There should be a backup job record, and its status should be STARTING
            if tasks_backup_job is None:
                logging.warning(fn_name + "No DB record for " + user_email)
                shared.serve_message_page(self, "No export job found. Please start a backup from the main menu.",
                    "If you believe this to be an error, please report this at the link below",
                    show_custom_button=True, custom_button_text='Go to main menu')
                logging.warning(fn_name + "<End> No DB record")
                logservice.flush()
                return
            
            if tasks_backup_job.status != constants.ExportJobStatus.STARTING:
                # The only time we should get here is if the credentials failed, and we were redirected after
                # successfully authorising. In that case, the jab status should still be STARTING
                shared.serve_message_page(self, "Job status: " + str(tasks_backup_job.status) + ". Please start a backup from the main menu.",
                    "If you believe this to be an error, please report this at the link below",
                    show_custom_button=True, custom_button_text='Go to main menu')
                logging.warning(fn_name + "<End> Invalid job status: " + str(tasks_backup_job.status))
                logservice.flush()
                return
                
            self._start_backup(tasks_backup_job)
            
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            shared.serve_outer_exception_message(self, e)
            logging.error(fn_name + "<End> due to exception" )
            logservice.flush()

        logging.debug(fn_name + "<End>")
        logservice.flush()
            
        
  
    def post(self):
        """ Handles GET request to settings.START_BACKUP_URL, which starts the backup process. """
        
        fn_name = "StartBackupHandler.post(): "
       
        logging.debug(fn_name + "<Start>")
        logservice.flush()

        try:
            # Only get the user here. The credentials are retrieved within _start_backup()
            # Don't need to check if user is logged in, because all pages (except '/') are set as secure in app.yaml
            user = users.get_current_user()
            user_email = user.email()
            
            
            # logging.debug(fn_name + "Resetting auth_count cookie to zero")
            # logservice.flush()
            

            is_test_user = shared.isTestUser(user_email)
            if self.request.host in settings.LIMITED_ACCESS_SERVERS:
                # logging.debug(fn_name + "Running on limited-access server")
                if not is_test_user:
                    logging.info(fn_name + "Rejecting non-test user on limited access server")
                    self.response.out.write("<h2>This is a test server. Access is limited to test users.</h2>")
                    logging.debug(fn_name + "<End> (restricted access)" )
                    logservice.flush()
                    return
            
            
            # if is_test_user:
              # logging.debug(fn_name + "POST args: include_hidden = " + str(self.request.get('include_hidden')) +
                                # ", include_completed = " + str(self.request.get('include_completed')) +
                                # ", include_deleted = " + str(self.request.get('include_deleted')))
                                
            logging.debug(fn_name + "Storing details for " + str(user_email))
            
      
            # Create a DB record, using the user's email address as the key
            tasks_backup_job = model.ProcessTasksJob(key_name=user_email)
            tasks_backup_job.user = user
            tasks_backup_job.job_type = 'export'
            tasks_backup_job.include_completed = (self.request.get('include_completed') == 'True')
            tasks_backup_job.include_deleted = (self.request.get('include_deleted') == 'True')
            tasks_backup_job.include_hidden = (self.request.get('include_hidden') == 'True')
            tasks_backup_job.put()

            logging.debug(fn_name + "include_hidden = " + str(tasks_backup_job.include_hidden) +
                                    ", include_completed = " + str(tasks_backup_job.include_completed) +
                                    ", include_deleted = " + str(tasks_backup_job.include_deleted))
            logservice.flush()

            
            
            # Forcing updated auth, so that worker has as much time as possible (i.e. one hour)
            # This is to combat situations where person authorises (e.g. when they start), but then does something
            # else for just under 1 hour before starting the backup. In that case, auth expires during the (max) 10 minutes 
            # that the worker is running (causing AccessTokenRefreshError: invalid_grant)
            # After authorisation, this URL will be called again as a GET, so we start the backup from the GET handler.
            logging.debug(fn_name + "Forcing auth, to get the freshest possible authorisation token")
            shared.redirect_for_auth(self, users.get_current_user())
            
            
            # # Try to start the export job now.
            # # _start_backup() will attempt to retrieve the user's credentials. If that fails, then
            # # the this URL will be called again as a GET, and we retry _start_backup() then
            # self._start_backup(tasks_backup_job)
                
            logging.debug(fn_name + "<End>")
            logservice.flush()
            
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            shared.serve_outer_exception_message(self, e)
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()

            
    def _start_backup(self, tasks_backup_job):
    
        fn_name = "StartBackupHandler._start_backup(): "
        logging.debug(fn_name + "<Start>")
        logservice.flush()
    
        try:
            ok, user, credentials, fail_msg, fail_reason = shared.get_credentials(self)
            if not ok:
                # User not logged in, or no or invalid credentials
                logging.warning(fn_name + "Error getting credentials: " + fail_msg + " - Redirecting for auth")
                shared.redirect_for_auth(self, user)
                return

            user_email = user.email()                
            
            tasks_backup_job.credentials = credentials
            tasks_backup_job.job_start_timestamp = datetime.datetime.now()
            tasks_backup_job.put()
            
            # Add the request to the tasks queue, passing in the user's email so that the task can access the
            # database record
            q = taskqueue.Queue(settings.PROCESS_TASKS_REQUEST_QUEUE_NAME)
            t = taskqueue.Task(url=settings.WORKER_URL, params={settings.TASKS_QUEUE_KEY_NAME : user_email}, method='POST')
            logging.debug(fn_name + "Adding task to " + str(settings.PROCESS_TASKS_REQUEST_QUEUE_NAME) + 
                " queue, for " + str(user_email))
            logservice.flush()
            
            try:
                q.add(t)
            except exception, e:
                logging.exception(fn_name + "Exception adding job to taskqueue. Redirecting to " + str(settings.PROGRESS_URL))
                logservice.flush()
                logging.debug(fn_name + "<End> (error adding job to taskqueue)")
                logservice.flush()
                # TODO: Redirect to retry page with a better/clearer message to user
                self.redirect(settings.PROGRESS_URL + "?msg=Exception%20adding%20job%20to%20taskqueue")
                return

            logging.debug(fn_name + "Redirecting to " + settings.PROGRESS_URL)
            logservice.flush()
            self.redirect(settings.PROGRESS_URL)
            
            logging.debug(fn_name + "<end>")
            logservice.flush()
    
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            shared.serve_outer_exception_message(self, e)
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()
    
    
    
class ShowProgressHandler(webapp.RequestHandler):
    """Handler to display progress to the user """
    
    def get(self):
        """Display the progress page, which includes a refresh meta-tag to recall this page every n seconds"""
        
        fn_name = "ShowProgressHandler.get(): "
    
        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        try:
            user = users.get_current_user()
            if not user:
                # User not logged in
                logging.info(fn_name + "No user information")
                logservice.flush()
                shared.redirect_for_auth(self, user)
                return
                
            client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.get_settings(self.request.host)
                
            user_email = user.email()
            if self.request.host in settings.LIMITED_ACCESS_SERVERS:
                # logging.debug(fn_name + "Running on limited-access server")
                if not shared.isTestUser(user_email):
                    logging.info(fn_name + "Rejecting non-test user on limited access server")
                    self.response.out.write("<h2>This is a test server. Access is limited to test users.</h2>")
                    logging.debug(fn_name + "<End> (restricted access)" )
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
                logging.error(fn_name + "No DB record for " + user_email)
                status = 'no-record'
                progress = 0
                job_start_timestamp = None
                job_msg = "No backup found for " + str(user_email)
            else:            
                # total_progress is only updated once all the tasks have been retrieved in a single tasklist.
                # tasklist_progress is updated every settings.TASK_COUNT_UPDATE_INTERVAL seconds within the retrieval process
                # for each tasklist. This ensures progress updates happen at least every settings.TASK_COUNT_UPDATE_INTERVAL seconds,
                # which wouldn't happen if it takes a long time to retrieve a large number of tasks in a single tasklist.
                # So, the current progress = total_progress + tasklist_progress
                status = tasks_backup_job.status
                error_message = tasks_backup_job.error_message
                progress = tasks_backup_job.total_progress + tasks_backup_job.tasklist_progress
                job_start_timestamp = tasks_backup_job.job_start_timestamp
                job_execution_time = datetime.datetime.now() - job_start_timestamp
                include_completed = tasks_backup_job.include_completed
                include_deleted = tasks_backup_job.include_deleted
                include_hidden = tasks_backup_job.include_hidden
                job_msg = tasks_backup_job.message
                
                #if status != 'completed' and status != 'export_completed' and status != 'error':
                #if not status in [constants.ExportJobStatus.EXPORT_COMPLETED, constants.ExportJobStatus.IMPORT_COMPLETED, constants.ExportJobStatus.ERROR ]:
                if not status in constants.ExportJobStatus.STOPPED_VALUES:
                    # Check if the job has exceeded either progress or total times
                    if job_execution_time.seconds > settings.MAX_JOB_TIME:
                        logging.error(fn_name + "Job created " + str(job_execution_time.seconds) + " seconds ago. Exceeded max allowed " +
                            str(settings.MAX_JOB_TIME))
                        error_message = "Job taking too long. Status was " + tasks_backup_job.status
                        if tasks_backup_job.error_message:
                            error_message = error_message + ", previous error was " + tasks_backup_job.error_message
                        status = 'job_exceeded_max_time'
                
                    time_since_last_update = datetime.datetime.now() - tasks_backup_job.job_progress_timestamp
                    if time_since_last_update.seconds > settings.MAX_JOB_PROGRESS_INTERVAL:
                        logging.error(fn_name + "Last job progress update was " + str(time_since_last_update.seconds) +
                            " seconds ago. Job appears to have stalled. Job was started " + str(job_execution_time.seconds) + 
                            " seconds ago at " + str(job_start_timestamp) + " UTC")
                        error_message = "Job appears to have stalled. Status was " + tasks_backup_job.status
                        if tasks_backup_job.error_message:
                            error_message = error_message + ", previous error was " + tasks_backup_job.error_message
                        status = 'job_stalled'
            
            if status == constants.ExportJobStatus.EXPORT_COMPLETED:
                logging.info(fn_name + "Retrieved " + str(progress) + " tasks for " + str(user_email))
            else:
                logging.debug(fn_name + "Status = " + str(status) + ", progress = " + str(progress) + 
                    " for " + str(user_email) + ", started at " + str(job_start_timestamp) + " UTC")
            
            if error_message:
                logging.warning(fn_name + "Error message: " + str(error_message))
            
            path = os.path.join(os.path.dirname(__file__), constants.PATH_TO_TEMPLATES, "progress.html")
            
            template_values = {'app_title' : app_title,
                               'host_msg' : host_msg,
                               'url_home_page' : settings.MAIN_PAGE_URL,
                               'product_name' : product_name,
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
                               'display_technical_options' : shared.isTestUser(user_email),
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
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            shared.serve_outer_exception_message(self, e)
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()
        

        
class ReturnResultsHandler(webapp.RequestHandler):
    """Handler to return results to user in the requested format """
    
    def get(self):
        """ If user attempts to go direct to /results, they come in a a GET request, so we redirect to /progress so user can choose format.
        
            This may also happen if credentials expire. The redirect_for_auth() method includes the current URL,
            but the OAuthHandler() can only redirect to a URL (not POST to it, because it no longer has the data).
            
            If we are here due to auth failure, the web page uses JavaScript to action the user's original selection
        """
        fn_name = "ReturnResultsHandler.get(): "
        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        try:
            logging.info(fn_name + "Expected POST for " + str(settings.RESULTS_URL) + 
                            "; May have been re-authentication when user selected an action, so redirecting to " + str(settings.PROGRESS_URL))
            logservice.flush()
            # Display the progress page to allow user to choose format for results
            self.redirect(settings.PROGRESS_URL)
            logging.debug(fn_name + "<End>")
            logservice.flush()
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            shared.serve_outer_exception_message(self, e)
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()
        
    def post(self):
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
                
        # except Exception, e:
            # logging.exception(fn_name + "Exception retrieving request headers")
            # logservice.flush()
            
      
        try:
            ok, user, credentials, fail_msg, fail_reason = shared.get_credentials(self)
            if not ok:
                # User not logged in, or no or invalid credentials
                shared.redirect_for_auth(self, user)
                return
            
            # User authentication is OK, so we are performing the user's action; 
            # delete the cookie (set negative age)
            shared.delete_cookie(self.response, 'actionId')
            
            client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.get_settings(self.request.host)
            
            user_email = user.email()
            is_test_user = shared.isTestUser(user_email)
            if self.request.host in settings.LIMITED_ACCESS_SERVERS:
                # logging.debug(fn_name + "Running on limited-access server")
                if not is_test_user:
                    logging.info(fn_name + "Rejecting non-test user on limited access server")
                    self.response.out.write("<h2>This is a test server. Access is limited to test users.</h2>")
                    logging.debug(fn_name + "<End> (restricted access)" )
                    logservice.flush()
                    return
            
            # Retrieve the DB record for this user
            tasks_backup_job = model.ProcessTasksJob.get_by_key_name(user_email)
                
            if tasks_backup_job is None:
                logging.error(fn_name + "No tasks_backup_job record for " + user_email)
                logservice.flush()
                job_start_timestamp = None
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
                        
            logging.debug(fn_name + "Selected format = " + str(export_format))
            logging.debug(fn_name + "Display options:" + 
                "\n    completed = "+ str(display_completed_tasks) +
                "\n    hidden    = "+ str(display_hidden_tasks) +
                "\n    deleted   = "+ str(display_deleted_tasks) +
                "\n    invalid   = "+ str(display_invalid_tasks))
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
                except Exception, e:
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
            #    Calculate and add 'depth' property (and add/modify elements for html_raw if required)
            # ---------------------------------------------------------------------------------------------
            for tasklist in tasklists:
                # if shared.isTestUser(user_email) and settings.DUMP_DATA:
                    # # DEBUG
                    # logging.debug(fn_name + "DEBUG: tasklist ==>")
                    # logging.debug(tasklist)
                    # logservice.flush()
                
                # If there are no tasks in a tasklist, Google returns a dictionary containing just 'title'
                # That is, there is no 'tasks' element in the tasklist dictionary if there are no tasks.
                tasks = tasklist.get(u'tasks')
                if not tasks:
                    # No tasks in tasklist
                    if shared.isTestUser(user_email):
                        logging.debug(fn_name + "Empty tasklist: '" + str(tasklist.get(u'title')) + "'")
                        logservice.flush()
                    continue
                
                num_tasks = len(tasks)
                if num_tasks > 0: # Non-empty tasklist
                    task_idx = 0
                    possible_parent_ids = []
                    possible_parent_is_active = []
                    
                    while task_idx < num_tasks:
                        task = tasks[task_idx]
                        # By default, assume parent is valid
                        task[u'parent_is_active'] = True
                        depth = 0 # Default to root task

                        if task.has_key(u'parent'):
                            if task[u'parent'] in possible_parent_ids:
                                idx = possible_parent_ids.index(task[u'parent'])
                                try:
                                    task[u'parent_is_active'] = possible_parent_is_active[idx]
                                except Exception, e:
                                    logging.exception("idx = " + str(idx) + ", id = " + task[u'id'] + ", parent = " + 
                                        task[u'parent'] + ", [" + task[u'title'] + "]")
                                    logservice.flush()
                                    # if shared.isTestUser(user_email):
                                        # # DEBUG
                                        # logging.debug(fn_name + "DEBUG: possible_parent_ids ==>")
                                        # logging(possible_parent_ids)
                                        # logging.debug(fn_name + "DEBUG: possible_parent_is_active ==>")
                                        # logging(possible_parent_is_active)
                                        # logservice.flush()
                                depth = idx + 1
                                
                                
                                # Remove parent tasks which are deeper than current parent
                                del(possible_parent_ids[depth:])
                                del(possible_parent_is_active[depth:])
                                    
                                if task[u'id'] not in possible_parent_ids:
                                    # This task may have sub-tasks, so add to list of possible  parents
                                    possible_parent_ids.append(task[u'id'])
                                    task_is_active = not (task.has_key(u'deleted') or task.has_key(u'hidden'))
                                    possible_parent_is_active.append(task_is_active)
                            else:
                                task[u'parent_is_active'] = False
                                if task.has_key(u'deleted') or task.has_key(u'hidden'):
                                    # Can't calculate depth of hidden and deleted tasks, if parent doesn't exist.
                                    # This usually happens if parent is deleted whilst child is hidden or deleted (see below)
                                    depth = -1
                                    total_num_orphaned_hidden_or_deleted_tasks = total_num_orphaned_hidden_or_deleted_tasks + 1
                                else:
                                    # Non-deleted/non-hidden task with invalid parent.
                                    # This "orphan" non-hidden/non-deleted task has an unknown depth, since it's parent no longer exists,
                                    # (or the completed parent was not exported - see below). 
                                    # (1) The parent task may have been deleted or moved.
                                    #       One way this can happen:
                                    #           Start with A/B/C/D
                                    #           Delete D
                                    #           Delete C
                                    #           Restore D from Trash
                                    #     This task is NOT displayed in any view by Google!
                                    # (2) This can also happen if a completed task has incomplete subtasks (which should not logically happen),
                                    #     and the user choses not to import completed tasks. In that case the incomplete subtask's completed 
                                    #     parent has not been imported, so GTB reports it as an orphaned (invalid) task.
                                    if display_invalid_tasks or export_format in ['raw', 'raw1', 'py', 'log']:
                                        depth = -99
                                        total_num_invalid_tasks = total_num_invalid_tasks + 1
                                    else:
                                        # Remove the invalid task
                                        tasks.pop(task_idx)
                                        # Adjust indexes to compensate for removed item
                                        task_idx = task_idx - 1
                                        num_tasks = num_tasks - 1
                                    
                        else:
                            # This is a parentless (root) task;
                            #   It is therefore the end of any potential sub-task tree
                            #   It could be the parent of a future task
                            possible_parent_ids = [task[u'id']]
                            task_is_active = not (task.has_key(u'deleted') or task.has_key(u'hidden'))
                            possible_parent_is_active = [task_is_active]
                            depth = 0
                        
                        task[u'depth'] = depth
                        task_idx = task_idx + 1   
                        
                    

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
                                    except Exception, e:
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
                            #     Unused properties: kind, id, etag, selfLink, parent, position, depth, parent_is_active
                            # 'kind', 'id', 'etag' are not used or displayed
                            # 'parent' is no longer needed, because we now use the indent property to display task/sub-task relationships
                            # 'position' is not needed because we rely on the fact that tasks are returned in position order
                            # 'depth' is no longer needed, because we use indent to determine how far in to render the task
                            # 'parent_is_active' only used when building the tasklist
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
                            if task.has_key(u'parent_is_active'):
                                del(task[u'parent_is_active'])

                        if tasklist_has_tasks_to_display:
                            tasklist[u'tasklist_has_tasks_to_display'] = True
            
            logservice.flush()
            logging.debug(fn_name + "total_num_orphaned_hidden_or_deleted_tasks = " + str(total_num_orphaned_hidden_or_deleted_tasks))
            logging.debug(fn_name + "total_num_invalid_tasks = " + str(total_num_invalid_tasks))
            logging.debug(fn_name + "num_not_displayed = " + str(num_not_displayed))
            logservice.flush()
                
            template_values = {'app_title' : app_title,
                               'host_msg' : host_msg,
                               'product_name' : product_name,
                               'tasklists': tasklists,
                               'include_completed' : include_completed, # Chosen at start of backup
                               'include_deleted' : include_deleted, # Chosen at start of backup
                               'include_hidden' : include_hidden, # Chosen at start of backup
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
            elif export_format in ['outlook', 'raw', 'raw1', 'log', 'import_export']:
                self._write_csv_using_template(template_values, export_format, output_filename_base)
            elif export_format == 'html_raw':
                self._write_html_raw(template_values)
            elif export_format == 'RTM':
                self._send_email_using_template(template_values, export_format, user_email, output_filename_base)
            elif export_format == 'py':
                self._write_text_using_template(template_values, export_format, output_filename_base, 'py')
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
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            
            self.response.headers["Content-Type"] = "text/html; charset=utf-8"
            try:
                # Clear "Content-Disposition" so user will see error in browser.
                # If not removed, output goes to file (if error generated after "Content-Disposition" was set),
                # and user would not see the error message!
                del self.response.headers["Content-Disposition"]
            except Exception, e:
                logging.debug(fn_name + "Unable to delete 'Content-Disposition' from headers: " + shared.get_exception_msg(e))
            self.response.clear() 
            shared.serve_outer_exception_message(self, e)
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()

        
    def _send_email_using_template(self, template_values, export_format, user_email, output_filename_base):
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
        
        # if shared.isTestUser(user_email):
          # logging.debug(fn_name + "Creating email body using template")
        # Use a template to convert all the tasks to the desired format 
        template_filename = "tasks_template_%s.txt" % export_format
        
        path = os.path.join(os.path.dirname(__file__), constants.PATH_TO_TEMPLATES, template_filename)
        email_body = template.render(path, template_values)

        # if shared.isTestUser(user_email):
          # logging.debug(fn_name + "Sending email")
        # TODO: Catch exception sending & display to user ??
        # According to "C:\Program Files\Google\google_appengine\google\appengine\api\mail.py", 
        #   end_mail() doesn't return any value, but can throw InvalidEmailError when invalid email address provided
        try:
            mail.send_mail(sender=user_email,
                           to=user_email,
                           subject=output_filename_base,
                           body=email_body)
        except apiproxy_errors.OverQuotaError:
            # Refer to https://developers.google.com/appengine/docs/quotas#When_a_Resource_is_Depleted
            logging.exception(fn_name + "Unable to send email")
            self.response.out.write("""Sorry, unable to send email due to quota limitations of my Appspot account.
                                       <br />
                                       It may be that your email is too large, or that too many emails have been sent by others in the past 24 hours.
                                       </br>
                                       Use your browser back button to return to the previous page.
                                    """)
            logging.debug(fn_name + "<End> (due to OverQuotaError)")
            logservice.flush()
            return
        except Exception, e:
            logging.exception(fn_name + "Unable to send email")
            self.response.out.write("""Unable to send email. 
                Please report the following error to <a href="http://%s">%s</a>
                <br />
                %s
                """ % (settings.url_issues_page, settings.url_issues_page, str(e)))
            logging.debug(fn_name + "<End> (due to exception)")
            logservice.flush()
            return
            
            
        if shared.isTestUser(user_email):
          logging.debug(fn_name + "Email sent to %s" % user_email)
        else:
          logging.debug(fn_name + "Email sent")
          
        # self.response.out.write("Email sent to %s </br>Use your browser back button to return to the previous page" % user_email)
        shared.serve_message_page(self, "Email sent to " + str(user_email), 
            show_back_button=True, back_button_text="Continue", show_heading_messages=False)
        
        #self.redirect("/completed")
        # logging.debug(fn_name + "Calling garbage collection")
        # gc.collect()
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
        output_filename = output_filename_base + ".ics"
        self.response.headers["Content-Type"] = "text/calendar"
        self.response.headers.add_header(
            "Content-Disposition", "attachment; filename=%s" % output_filename)

        path = os.path.join(os.path.dirname(__file__), constants.PATH_TO_TEMPLATES, template_filename)
        if shared.isTestUser(template_values['user_email']):
          logging.debug(fn_name + "Writing %s format to %s" % (export_format, output_filename))
        else:
          logging.debug(fn_name + "Writing %s format" % export_format)
        self.response.out.write(template.render(path, template_values))
        # logging.debug(fn_name + "Calling garbage collection")
        # gc.collect()
        logging.debug(fn_name + "<End>")
        logservice.flush()
        

    def _write_csv_using_template(self, template_values, export_format, output_filename_base):
        """ Write a CSV file according to the specified .csv template file
            Currently supports export_format = 'outlook', 'raw', 'raw1' and 'import_export'
        """
        fn_name = "_write_csv_using_template(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        template_filename = "tasks_template_%s.csv" % export_format
        output_filename = output_filename_base + ".csv"
        self.response.headers["Content-Type"] = "text/csv"
        self.response.headers.add_header(
            "Content-Disposition", "attachment; filename=%s" % output_filename)

        
        path = os.path.join(os.path.dirname(__file__), constants.PATH_TO_TEMPLATES, template_filename)
        if shared.isTestUser(template_values['user_email']):
          logging.debug(fn_name + "Writing %s format to %s" % (export_format, output_filename))
        else:
          logging.debug(fn_name + "Writing %s format" % export_format)
        self.response.out.write(template.render(path, template_values))
        # logging.debug(fn_name + "Calling garbage collection")
        # gc.collect()
        logging.debug(fn_name + "<End>")
        logservice.flush()


    def _write_text_using_template(self, template_values, export_format, output_filename_base, file_extension):
        """ Write a TXT file according to the specified .txt template file
            Currently supports export_format = 'py' 
        """
        fn_name = "_write_text_using_template(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        template_filename = "tasks_template_%s.%s" % (export_format, file_extension)
        output_filename = output_filename_base + "." + file_extension
        self.response.headers["Content-Type"] = "text/plain"
        self.response.headers.add_header(
            "Content-Disposition", "attachment;filename=%s" % output_filename)

        
        path = os.path.join(os.path.dirname(__file__), constants.PATH_TO_TEMPLATES, template_filename)
        if shared.isTestUser(template_values['user_email']):
          logging.debug(fn_name + "Writing %s format to %s" % (export_format, output_filename))
        else:
          logging.debug(fn_name + "Writing %s format" % export_format)
        # TODO: Output in a manner suitable for downloading from an Android phone
        #       Currently sends source of HTML page as output_filename
        #       Perhaps try Content-Type = "application/octet-stream" ???
        self.response.out.write(template.render(path, template_values))
        # logging.debug(fn_name + "Calling garbage collection")
        # gc.collect()
        logging.debug(fn_name + "<End>")
        logservice.flush()

        
    def _write_gtbak_format(self, tasklists, export_format, output_filename_base):
        fn_name = "_write_raw_file(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
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
                date_due = task.get(u'due')
                if date_due:
                    gtb_task[u'due'] = date_due.strftime("UTC %Y-%m-%d") # import-tasks requires a string
                completed = task.get(u'completed')
                if completed:
                    gtb_task[u'completed'] = completed.strftime("UTC %Y-%m-%d %H:%M:%S") # import-tasks requires a string
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

        
    def _write_raw_file(self, file_content, export_format, output_filename_base, file_extension, content_type="text/plain", content_prefix=None):
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
        
        output_filename = output_filename_base + "." + file_extension
        self.response.headers["Content-Type"] = content_type
        self.response.headers.add_header(
            "Content-Disposition", "attachment;filename=%s" % output_filename)
        logging.debug(fn_name + "Writing " + str(export_format) + " format file")
        if content_prefix:
            self.response.out.write(content_prefix)
        self.response.out.write(file_content)
        logging.debug(fn_name + "<End>")
        logservice.flush()

        
    def _write_html_raw(self, template_values):
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
        self.response.out.write("""<div class="usertitle">Authorised user: """)
    
        self.response.out.write(user_email)
        self.response.out.write(' <span class="logout-link">[ <a href="')
        self.response.out.write(logout_url)
        self.response.out.write('">Log out</a> ]</span></div>')
        
        self.response.out.write("""<div class="break">""") # Div to contain Back and Print buttons on same row. Don't print buttons.
        # self.response.out.write("""<div class="break no-print"><button onclick="javascript:history.back(-1)" class="back-button"  value="Back">Back</button></div>""")
        
        # Need to provide the specific URL of the progress page. We can't use history.back() because the user may have used 
        # the next/previous tasklist links one or more times.
        self.response.out.write("""<div class="no-print" style="float: left;"><button onclick="window.location.href = '%s'" class="back-button"  value="Back">Back</button></div>""" % settings.RESULTS_URL)
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
                if len(tasklist_title.strip()) == 0:
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
                        if len(task_title.strip()) == 0:
                            task_title = "<Unnamed Task>"
                        task_title = shared.escape_html(task_title)
                        
                        task_notes = shared.escape_html(task.get(u'notes', None))
                        task_deleted = task.get(u'deleted', None)
                        task_hidden = task.get(u'hidden', None)
                        task_invalid = task.get(u'invalid', False)
                        task_indent = str(task.get('indent', 0))
                        
                        
                        if u'due' in task:
                            task_due = task[u'due'].strftime('%a, %d %b %Y') + " UTC"
                        else:
                            task_due = None
                            
                        if u'updated' in task:
                            task_updated = task[u'updated'].strftime('%H:%M:%S %a, %d %b %Y') + " UTC"
                        else:
                            task_updated = None
                        
                        if task.get(u'status') == 'completed':
                            task_completed = True
                        else:
                            task_completed = False
                            
                        if u'completed' in task:
                            # We assume that this is only set when the task is completed
                            task_completed_date = task[u'completed'].strftime('%H:%M %a, %d %b %Y') + " UTC"
                            task_status_str = "&#x2713;"
                        else:
                            task_completed_date = ''
                            task_status_str = "[ &nbsp;]"
                        
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
                  'app_title' : app_title,
                  'app_version' : app_version }
            )

        self.response.out.write("""</body></html>""")
        tasklists = None
        gc.collect()
        logging.debug(fn_name + "<End>")
        logservice.flush()
               
        
    
class InvalidCredentialsHandler(webapp.RequestHandler):
    """Handler for /invalidcredentials"""

    def get(self):
        """Handles GET requests for /invalidcredentials"""

        fn_name = "InvalidCredentialsHandler.get(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        try:
            # DEBUG
            # if self.request.cookies.has_key('auth_count'):
                # logging.debug(fn_name + "Cookie: auth_count = " + str(self.request.cookies['auth_count']))
            # else:
                # logging.debug(fn_name + "No auth_count cookie found")
            # logservice.flush()            
                
            client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.get_settings(self.request.host)
            
            path = os.path.join(os.path.dirname(__file__), constants.PATH_TO_TEMPLATES, "invalid_credentials.html")

            template_values = {  'app_title' : app_title,
                                 'app_version' : appversion.version,
                                 'upload_timestamp' : appversion.upload_timestamp,
                                 'rc' : self.request.get('rc'),
                                 'nr' : self.request.get('nr'),
                                 'err' : self.request.get('err'),
                                 'AUTH_RETRY_COUNT_COOKIE_EXPIRATION_TIME' : settings.AUTH_RETRY_COUNT_COOKIE_EXPIRATION_TIME,
                                 'host_msg' : host_msg,
                                 'url_main_page' : settings.MAIN_PAGE_URL,
                                 'url_home_page' : settings.MAIN_PAGE_URL,
                                 'product_name' : product_name,
                                 'url_discussion_group' : settings.url_discussion_group,
                                 'email_discussion_group' : settings.email_discussion_group,
                                 'url_issues_page' : settings.url_issues_page,
                                 'url_source_code' : settings.url_source_code,
                                 'logout_url': users.create_logout_url(settings.WELCOME_PAGE_URL)}
                         
            self.response.out.write(template.render(path, template_values))
            # logging.debug(fn_name + "Writing cookie: Resetting auth_count cookie to zero")
            # logservice.flush()
            
            logging.debug(fn_name + "<End>")
            logservice.flush()
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            shared.serve_outer_exception_message(self, e)
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()
       
       
        
class CompletedHandler(webapp.RequestHandler):
    """Handler for /completed."""

    def get(self):
        """Handles GET requests for /completed"""
        fn_name = "CompletedHandler.get(): "

        logging.debug(fn_name + "<Start>" )
        logservice.flush()
                
        try:
            # DEBUG
            # if self.request.cookies.has_key('auth_count'):
                # logging.debug(fn_name + "Cookie: auth_count = " + str(self.request.cookies['auth_count']))
            # else:
                # logging.debug(fn_name + "No auth_count cookie found")
            # logservice.flush()            
                
            ok, user, credentials, fail_msg, fail_reason = shared.get_credentials(self)
            if not ok:
                # User not logged in, or no or invalid credentials
                shared.redirect_for_auth(self, user)
                return
                
                
            user_email = user.email()

            client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.get_settings(self.request.host)

            path = os.path.join(os.path.dirname(__file__), constants.PATH_TO_TEMPLATES, "completed.html")
            if not credentials or credentials.invalid:
                is_authorized = False
            else:
                is_authorized = True
                # logging.debug(fn_name + "Resetting auth_count cookie to zero")
                # logservice.flush()
                
                
            template_values = {'app_title' : app_title,
                                 'host_msg' : host_msg,
                                 'url_main_page' : settings.MAIN_PAGE_URL,
                                 'url_home_page' : settings.MAIN_PAGE_URL,
                                 'product_name' : product_name,
                                 'is_authorized': is_authorized,
                                 'user_email' : user_email,
                                 'logout_url': users.create_logout_url(settings.WELCOME_PAGE_URL),
                                 'msg': self.request.get('msg'),
                                 'url_discussion_group' : settings.url_discussion_group,
                                 'email_discussion_group' : settings.email_discussion_group,
                                 'url_issues_page' : settings.url_issues_page,
                                 'url_source_code' : settings.url_source_code,
                                 'logout_url': users.create_logout_url(settings.WELCOME_PAGE_URL)}
            self.response.out.write(template.render(path, template_values))
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            shared.serve_outer_exception_message(self, e)
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()

      
      
class AuthHandler(webapp.RequestHandler):
    """Handler for /auth."""

    def get(self):
        """Handles GET requests for /auth."""
        fn_name = "AuthHandler.get() "
        
        logging.debug(fn_name + "<Start>" )
        logservice.flush()
        
        try:
                
            ok, user, credentials, fail_msg, fail_reason = shared.get_credentials(self)
            if ok:
                if shared.isTestUser(user.email()):
                    logging.debug(fn_name + "Existing credentials for " + str(user.email()) + ", expires " + 
                        str(credentials.token_expiry) + " UTC")
                else:
                    logging.debug(fn_name + "Existing credentials expire " + str(credentials.token_expiry) + " UTC")
                logging.debug(fn_name + "User is authorised. Redirecting to " + settings.MAIN_PAGE_URL)
                self.redirect(settings.MAIN_PAGE_URL)
            else:
                shared.redirect_for_auth(self, user)
            
            logging.debug(fn_name + "<End>" )
            logservice.flush()
            
        except shared.DailyLimitExceededError, e:
            logging.warning(fn_name + e.msg)
            self.response.out.write(e.msg)
            logging.debug(fn_name + "<End> (Daily Limit Exceeded)")
            logservice.flush()
            
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            shared.serve_outer_exception_message(self, e)
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()

            
    
class OAuthCallbackHandler(webapp.RequestHandler):
    """Handler for /oauth2callback."""

    def get(self):
        """Handles GET requests for /oauth2callback."""
        
        fn_name = "OAuthCallbackHandler.get() "
        
        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        shared.handle_auth_callback(self)
        
        logging.debug(fn_name + "<End>")
        logservice.flush()
        

def real_main():
    logging.debug("main(): Starting tasks-backup (app version %s)" %appversion.version)
    template.register_template_library("common.customdjango")

    application = webapp.WSGIApplication(
        [
            (settings.MAIN_PAGE_URL,                    MainHandler),
            (settings.WELCOME_PAGE_URL,                 WelcomeHandler),
            (settings.RESULTS_URL,                      ReturnResultsHandler),
            (settings.START_BACKUP_URL,                 StartBackupHandler),
            (settings.PROGRESS_URL,                     ShowProgressHandler),
            (settings.INVALID_CREDENTIALS_URL,          InvalidCredentialsHandler),
            ("/completed",                              CompletedHandler),
            ("/auth",                                   AuthHandler),
            ("/oauth2callback",                         OAuthCallbackHandler),
        ], debug=False)
    util.run_wsgi_app(application)
    logging.debug("main(): <End>")
    logservice.flush()

def profile_main():
    # From https://developers.google.com/appengine/kb/commontasks#profiling
    # This is the main function for profiling
    # We've renamed our original main() above to real_main()
    import cProfile, pstats, StringIO
    prof = cProfile.Profile()
    prof = prof.runctx("real_main()", globals(), locals())
    stream = StringIO.StringIO()
    stats = pstats.Stats(prof, stream=stream)
    stats.sort_stats("time")  # Or cumulative
    stats.print_stats(80)  # 80 = how many to print
    # The rest is optional.
    stats.print_callees()
    stats.print_callers()
    logging.info("Profile data:\n%s", stream.getvalue())
    logservice.flush()
    
main = real_main

if __name__ == "__main__":
    main()

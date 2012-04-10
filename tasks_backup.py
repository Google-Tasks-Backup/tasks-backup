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

# 27 Jan 2012, Google Tasks Backup (tasks-backup), based on Google Tasks Porter

"""Main web application handler for Google Tasks Backup."""

# Orig __author__ = "dwightguth@google.com (Dwight Guth)"
__author__ = "julie.smith.1999@gmail.com (Julie Smith)"

import logging
import os
import pickle
import sys
import gc
import cgi

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

logservice.AUTOFLUSH_EVERY_SECONDS = 5
logservice.AUTOFLUSH_EVERY_BYTES = None
logservice.AUTOFLUSH_EVERY_LINES = 5
logservice.AUTOFLUSH_ENABLED = True

import httplib2

import model
import settings
import datetime
from datetime import timedelta
import appversion # appversion.version is set before the upload process to keep the version number consistent
import shared # Code whis is common between tasks-backup.py and worker.py


  
def _RedirectForOAuth(self, user):
  """Redirects the webapp response to authenticate the user with OAuth2."""
  
  client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)
  
  flow = client.OAuth2WebServerFlow(
      client_id=client_id,
      client_secret=client_secret,
      scope="https://www.googleapis.com/auth/tasks",
      user_agent=user_agent,
      xoauth_displayname=product_name,
      state=self.request.path_qs)

  callback = self.request.relative_url("/oauth2callback")
  authorize_url = flow.step1_get_authorize_url(callback)
  memcache.set(user.user_id(), pickle.dumps(flow))
  logging.debug("_RedirectForOAuth(): Redirecting to " + str(authorize_url))
  self.redirect(authorize_url)


  
def _GetCredentials():
  user = users.get_current_user()
  credentials = appengine.StorageByKeyName(
      model.Credentials, user.user_id(), "credentials").get()

  # so it turns out that the method that checks if the credentials are okay
  # doesn't give the correct answer unless you try to refresh it.  So we do that
  # here in order to make sure that the credentials are valid before being
  # passed to a worker.  Obviously if the user revokes the credentials after
  # this point we will continue to get an error, but we can't stop that.

  if credentials and not credentials.invalid:
    try:
      http = httplib2.Http()
      http = credentials.authorize(http)
      service = discovery.build("tasks", "v1", http)
      tasklists = service.tasklists()
      tasklists_list = tasklists.list().execute()
    except:
      credentials = None

  return user, credentials
  
  
class InvalidCredentialsHandler(webapp.RequestHandler):
    """Handler for /invalidcredentials"""

    def get(self):
        """Handles GET requests for /invalidcredentials"""

        fn_name = "InvalidCredentialsHandler.get(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)
        
        path = os.path.join(os.path.dirname(__file__), "invalid_credentials.html")

        template_values = {  'app_title' : app_title,
                             'app_version' : appversion.version,
                             'upload_timestamp' : appversion.upload_timestamp,
                             'host_msg' : host_msg,
                             'home_page_url' : settings.HOME_PAGE_URL,
                             'product_name' : product_name,
                             'url_discussion_group' : settings.url_discussion_group,
                             'email_discussion_group' : settings.email_discussion_group,
                             'url_issues_page' : settings.url_issues_page,
                             'url_source_code' : settings.url_source_code,
                             'logout_url': users.create_logout_url('/')}
                     
        self.response.out.write(template.render(path, template_values))
        logging.debug(fn_name + "<End>")
        
        
class MainHandler(webapp.RequestHandler):
    """Handler for /."""

    def get(self):
        """Handles GET requests for /."""

        fn_name = "MainHandler.get(): "

        logging.info(fn_name + "<Start> (app version %s)" %appversion.version )
        logservice.flush()
        
        client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)

        logging.debug(fn_name + "Calling _GetCredentials()")
        user, credentials = _GetCredentials()
            
        if user:
            user_email = user.email()
        
        if shared.isTestUser(user_email):
            logging.debug(fn_name + "Started by test user %s" % user_email)
            
            try:
                headers = self.request.headers
                for k,v in headers.items():
                    logging.debug(fn_name + "browser header: " + str(k) + " = " + str(v))
                    
            except Exception, e:
                logging.exception(fn_name + "Exception retrieving request headers")
                
        # # Log and flush before starting operation which may cause memory limit exceeded error
        # logging.debug(fn_name + "building template")
        # logservice.flush() 
        
        path = os.path.join(os.path.dirname(__file__), "index.html")
        if not credentials or credentials.invalid:
            is_authorized = False
        else:
            is_authorized = True
            if self.request.host in settings.LIMITED_ACCESS_SERVERS:
                logging.info(fn_name + "Running on limited-access server")
                if not shared.isTestUser(user_email):
                    logging.info(fn_name + "Rejecting non-test user on limited access server")
                    self.response.out.write("<h2>This is a test server. Access is limited to test users.</h2>")
                    logging.debug(fn_name + "<End> (restricted access)" )
                    logservice.flush()
                    return

          
        template_values = {'app_title' : app_title,
                           'host_msg' : host_msg,
                           'home_page_url' : settings.HOME_PAGE_URL,
                           'product_name' : product_name,
                           'is_authorized': is_authorized,
                           'user_email' : user_email,
                           'start_backup_url' : settings.START_BACKUP_URL,
                           'msg': self.request.get('msg'),
                           'logout_url': users.create_logout_url('/'),
                           'url_discussion_group' : settings.url_discussion_group,
                           'email_discussion_group' : settings.email_discussion_group,
                           'url_issues_page' : settings.url_issues_page,
                           'url_source_code' : settings.url_source_code,
                           'app_version' : appversion.version,
                           'upload_timestamp' : appversion.upload_timestamp}
        self.response.out.write(template.render(path, template_values))
        # logging.debug(fn_name + "Calling garbage collection")
        # gc.collect()
        logging.debug(fn_name + "<End>" )
        logservice.flush()
    

class AuthRedirectHandler(webapp.RequestHandler):
  """Handler for /auth."""

  def get(self):
    """Handles GET requests for /auth."""
    user, credentials = _GetCredentials()

    if not credentials or credentials.invalid:
      _RedirectForOAuth(self, user)
    else:
      self.redirect("/")


# class AuthRedirectHandler(webapp.RequestHandler):
  # """Handler for /auth."""

  # def get(self):
    # """Handles GET requests for /auth."""
    # fn_name = "AuthRedirectHandler.get() "
    
    # user, credentials = _GetCredentials()

    # if not credentials:
        # logging.debug(fn_name + "No credentials. Calling _RedirectForOAuth()")
        # logging.debug(fn_name + "user ==>")
        # shared.DumpObj(user)
        # logging.debug(fn_name + "credentials ==>")
        # shared.DumpObj(credentials)
        # logservice.flush()
        # _RedirectForOAuth(self, user)
    # elif credentials.invalid:
        # logging.warning(fn_name + "Invalid credentials. Redirecting to " + settings.INVALID_CREDENTIALS_URL)
        # logging.debug(fn_name + "user ==>")
        # shared.DumpObj(user)
        # logging.debug(fn_name + "credentials ==>")
        # shared.DumpObj(credentials)
        # logservice.flush()
        # self.redirect(settings.INVALID_CREDENTIALS_URL)
    # else:
        # logging.debug(fn_name + "Credentials valid. Redirecting to /")
        # logservice.flush()
        # self.redirect("/")

      
    
class CompletedHandler(webapp.RequestHandler):
    """Handler for /completed."""

    def get(self):
        """Handles GET requests for /completed"""
        fn_name = "CompletedHandler.get(): "

        user, credentials = _GetCredentials()
        # if user is None:
            # logging.warning(fn_name + "user is None, redirecting to " +
                # settings.INVALID_CREDENTIALS_URL)
            # self.redirect(settings.INVALID_CREDENTIALS_URL)
            # return
            
        # if credentials is None or credentials.invalid:
            # logging.warning(fn_name + "credentials is None or invalid, redirecting to " + 
                # settings.INVALID_CREDENTIALS_URL)
            # self.redirect(settings.INVALID_CREDENTIALS_URL)
            # return
            
        user_email = user.email()
        if isUserEmail(user_email):
            logging.debug(fn_name + "user_email = [%s]" % user_email)

        client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)

        
        # Log and flush before starting operation which may cause memory limit exceeded error
        logging.debug(fn_name + "building template")
        logservice.flush() 
        
        path = os.path.join(os.path.dirname(__file__), "completed.html")
        if not credentials or credentials.invalid:
            is_authorized = False
        else:
            is_authorized = True
            
        template_values = {'app_title' : app_title,
                             'host_msg' : host_msg,
                             'home_page_url' : settings.HOME_PAGE_URL,
                             'product_name' : product_name,
                             'is_authorized': is_authorized,
                             'user_email' : user_email,
                             'msg': self.request.get('msg'),
                             'url_discussion_group' : settings.url_discussion_group,
                             'email_discussion_group' : settings.email_discussion_group,
                             'url_issues_page' : settings.url_issues_page,
                             'url_source_code' : settings.url_source_code,
                             'logout_url': users.create_logout_url('/')}
        self.response.out.write(template.render(path, template_values))

      
class StartBackupHandler(webapp.RequestHandler):
    """ Handler to start the backup process. """
    
  
    def post(self):
        """ Handles GET request to settings.START_BACKUP_URL, which starts the backup process. """
        
        fn_name = "StartBackupHandler.post(): "
       
        logging.debug(fn_name + "<Start>")
        logservice.flush()

        # client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)
        
        user, credentials = _GetCredentials()
        if user is None:
            logging.warning(fn_name + "user is None, redirecting to " +
                settings.INVALID_CREDENTIALS_URL)
            logservice.flush()
            self.redirect(settings.INVALID_CREDENTIALS_URL)
            return
            
        if credentials is None or credentials.invalid:
            logging.warning(fn_name + "credentials is None or invalid, redirecting to " + 
                settings.INVALID_CREDENTIALS_URL)
            logservice.flush()
            self.redirect(settings.INVALID_CREDENTIALS_URL)
            return
            
        user_email = user.email()
        is_test_user = shared.isTestUser(user_email)
        if self.request.host in settings.LIMITED_ACCESS_SERVERS:
            logging.info(fn_name + "Running on limited-access server")
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
        tasks_backup_job = model.TasksBackupJob(key_name=user_email)
        tasks_backup_job.include_completed = (self.request.get('include_completed') == 'True')
        tasks_backup_job.include_deleted = (self.request.get('include_deleted') == 'True')
        tasks_backup_job.include_hidden = (self.request.get('include_hidden') == 'True')
        tasks_backup_job.user = user
        tasks_backup_job.credentials = credentials
        tasks_backup_job.put()

        logging.debug(fn_name + "include_hidden = " + str(tasks_backup_job.include_hidden) +
                                ", include_completed = " + str(tasks_backup_job.include_completed) +
                                ", include_deleted = " + str(tasks_backup_job.include_deleted))
        logservice.flush()
        
        # Add the task to the taskqueue
        # Add the request to the tasks queue, passing in the user's email so that the task can access the
        # databse record
        q = taskqueue.Queue(settings.BACKUP_REQUEST_QUEUE_NAME)
        t = taskqueue.Task(url='/worker', params={settings.TASKS_QUEUE_KEY_NAME : user_email}, method='POST')
        logging.info(fn_name + "Adding task to " + str(settings.BACKUP_REQUEST_QUEUE_NAME) + 
            " queue, for " + str(user_email))
        logservice.flush()
        
        try:
            q.add(t)
        except exception, e:
            logging.exception(fn_name + "Exception adding task to taskqueue. Redirecting to " + str(settings.PROGRESS_URL))
            logservice.flush()
            self.redirect(settings.PROGRESS_URL + "?msg=Exception%20adding%20task%20to%20taskqueue")
            return

        logging.debug(fn_name + "Redirect to " + settings.PROGRESS_URL + " for " + str(user_email))
        logservice.flush()
        self.redirect(settings.PROGRESS_URL)
        # logging.debug(fn_name + "Calling garbage collection")
        # gc.collect()
        logging.debug(fn_name + "<End> for " + str(user_email))
        logservice.flush()

        
class ShowProgressHandler(webapp.RequestHandler):
    """Handler to display progress to the user """
    
    def get(self):
        # TODO: Display the progress page, which includes a refresh meta-tag to recall this page every n seconds
        fn_name = "ShowProgressHandler.get(): "
    
        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)
      
          
        user, credentials = _GetCredentials()
        if user is None:
            logging.warning(fn_name + "user is None, redirecting to " +
                settings.INVALID_CREDENTIALS_URL)
            logservice.flush()
            self.redirect(settings.INVALID_CREDENTIALS_URL)
            return
            
        if credentials is None or credentials.invalid:
            logging.warning(fn_name + "credentials is None or invalid, redirecting to " + 
                settings.INVALID_CREDENTIALS_URL)
            logservice.flush()
            self.redirect(settings.INVALID_CREDENTIALS_URL)
            return
            
            
        user_email = user.email()
        if self.request.host in settings.LIMITED_ACCESS_SERVERS:
            logging.info(fn_name + "Running on limited-access server")
            if not shared.isTestUser(user_email):
                logging.info(fn_name + "Rejecting non-test user on limited access server")
                self.response.out.write("<h2>This is a test server. Access is limited to test users.</h2>")
                logging.debug(fn_name + "<End> (restricted access)" )
                logservice.flush()
                return
        
        
        # Retrieve the DB record for this user
        tasks_backup_job = model.TasksBackupJob.get_by_key_name(user_email)
            
        if tasks_backup_job is None:
            logging.error(fn_name + "No DB record for " + user_email)
            status = 'error'
            progress = 0
            error_message = "No backup job found for " + str(user_email) + ", please restart."
            job_start_timestamp = None
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
            
            if status != 'completed' and status != 'error':
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
                    
        logging.debug(fn_name + "Status = " + str(status) + ", progress = " + str(progress) + 
            " for " + str(user_email) + ", started at " + str(job_start_timestamp) + " UTC")
        
        if error_message:
            logging.error(fn_name + "Error message: " + str(error_message))
        
        # Log and flush before starting operation which may cause memory limit exceeded error
        # logging.debug(fn_name + "building template")
        # logservice.flush() 
        
        path = os.path.join(os.path.dirname(__file__), "progress.html")
        
        #refresh_url = self.request.host + '/' + settings.PROGRESS_URL
        
        template_values = {'app_title' : app_title,
                           'host_msg' : host_msg,
                           'home_page_url' : settings.HOME_PAGE_URL,
                           'product_name' : product_name,
                           'status' : status,
                           'progress' : progress,
                           'include_completed' : include_completed,
                           'include_deleted' : include_deleted,
                           'include_hidden' : include_hidden,
                           'error_message' : error_message,
                           'job_start_timestamp' : job_start_timestamp,
                           'refresh_interval' : settings.PROGRESS_PAGE_REFRESH_INTERVAL,
                           'large_list_html_warning_limit' : settings.LARGE_LIST_HTML_WARNING_LIMIT,
                           'user_email' : user_email,
                           'display_technical_options' : shared.isTestUser(user_email),
                           'results_url' : settings.RESULTS_URL,
                           #'start_backup_url' : settings.START_BACKUP_URL,
                           #'refresh_url' : settings.PROGRESS_URL,
                           'msg': self.request.get('msg'),
                           'logout_url': users.create_logout_url('/'),
                           'url_discussion_group' : settings.url_discussion_group,
                           'email_discussion_group' : settings.email_discussion_group,
                           'url_issues_page' : settings.url_issues_page,
                           'url_source_code' : settings.url_source_code,
                           'app_version' : appversion.version,
                           'upload_timestamp' : appversion.upload_timestamp}
        self.response.out.write(template.render(path, template_values))
        # logging.debug(fn_name + "Calling garbage collection")
        # gc.collect()
        logging.debug(fn_name + "<End>")
        logservice.flush()
        
          
class ReturnResultsHandler(webapp.RequestHandler):
    """Handler to return results to user in the requested format """
    
    def get(self):
        fn_name = "ReturnResultsHandler.get(): "
        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        logging.warning(fn_name + "Expected POST for " + str(settings.RESULTS_URL) + 
                        ", so redirecting to " + str(settings.PROGRESS_URL))
        logservice.flush()
        # Display the progress page to allow user to choose format for results
        self.redirect(settings.PROGRESS_URL)
        # logging.debug(fn_name + "Calling garbage collection")
        # gc.collect()
        logging.debug(fn_name + "<End>")
        logservice.flush()
        
    def post(self):
        """ Return results to the user, in format chosen by user """
        fn_name = "ReturnResultsHandler.post(): "
        
        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)
        
        user, credentials = _GetCredentials()
        if user is None:
            logging.warning(fn_name + "user is None, redirecting to " +
                settings.INVALID_CREDENTIALS_URL)
            logservice.flush()
            self.redirect(settings.INVALID_CREDENTIALS_URL)
            return
            
        if credentials is None or credentials.invalid:
            logging.warning(fn_name + "credentials is None or invalid, redirecting to " + 
                settings.INVALID_CREDENTIALS_URL)
            logservice.flush()
            self.redirect(settings.INVALID_CREDENTIALS_URL)
            return
            
        user_email = user.email()
        is_test_user = shared.isTestUser(user_email)
        if self.request.host in settings.LIMITED_ACCESS_SERVERS:
            logging.info(fn_name + "Running on limited-access server")
            if not is_test_user:
                logging.info(fn_name + "Rejecting non-test user on limited access server")
                self.response.out.write("<h2>This is a test server. Access is limited to test users.</h2>")
                logging.debug(fn_name + "<End> (restricted access)" )
                logservice.flush()
                return
        
        # Retrieve the DB record for this user
        logging.debug(fn_name + "Retrieving details for " + str(user_email))
        
        tasklists_records = db.GqlQuery("SELECT * "
                                        "FROM TasklistsData "
                                        "WHERE ANCESTOR IS :1 "
                                        "ORDER BY idx ASC",
                                        db.Key.from_path(settings.DB_KEY_TASKS_DATA, user_email))

        num_records = tasklists_records.count()
        
        if num_records is None:
            # There should be at least one record, since we will only execute this function if TasksBackupJob.status == completed
            # Possibly user got here by doing a POST without starting a backup request first 
            # (e.g. page refresh from an old job)
            logging.error(fn_name + "No data records found for " + str(user_email))
            # TODO: Display better error to user &/or redirect to allow user to start a backup job
            self.response.set_status(412, "No data for this user. Please retry backup request.")
            return
        
        logging.debug("Reassembling tasks data from " + str(num_records) + " blobs")
        rebuilt_pkl = ""
        for tasklists_record in tasklists_records:
            #logging.debug("Reassembling blob number " + str(tasklists_record.idx))
            rebuilt_pkl = rebuilt_pkl + tasklists_record.pickled_tasks_data
            
        logging.debug("Reassembled " + str(len(rebuilt_pkl)) + " bytes")
        
        tasklists = pickle.loads(rebuilt_pkl)
        rebuilt_pkl = None # Not needed, so release it
        
        # ------------------------------------------------------
        #               Return the data to the user
        # ------------------------------------------------------
        
        #      self.WriteDebugHtmlTemplate(debugmessage, datadump1, datadump2, datadump3, datadump4)
        
        # if is_test_user:
          # logging.debug(fn_name + "Writing template data")


        """
          Structure used in Django CSV templates
            {% for tasklist in tasklists %}
              {% for task in tasklist.tasks %}
              
          Structure to pass to django
          {
            "now": datetime.datetime.now(),  # Timestamp for the creation of this report/backup
            "tasklists": [ tasklist ]        # List of tasklist items
          }
          
          structure of tasklist
          { 
            "title" : tasklist.title,        # Name of this tasklist
            "tasks"  : [ task ]              # List of task items in this tasklist
          }
          
          structure of task
          {
            "title" : title, # Free text
            "status" : status, # "completed" | "needsAction"
            "id" : id, # Used when determining parent-child relationships
            "parent" : parent, # OPT: ID of the parent of this task (only if this is a sub-task)
            "notes" : notes, # OPT: Free text
            "due" : due, # OPT: Date due, e.g. 2012-01-30T00:00:00.000Z NOTE time = 0
            "updated" : updated, # Timestamp, e.g., 2012-01-26T07:47:18.000Z
            "completed" : completed # Timestamp, e.g., 2012-01-27T10:38:56.000Z
          }

        """
          
        # User chose which format to export as
        export_format = self.request.get("format")
        
        # We pass the job_start_timestamp from the Progress page so that we can display it on the HTML page
        job_start_timestamp = self.request.get('job_start_timestamp')
        
        # User selected HTML display options (used when format == html)
        dim_completed_tasks = (self.request.get('dim_completed_tasks') == 'True')
        display_completed_date_field = (self.request.get('display_completed_date_field') == 'True')
        display_due_date_field = (self.request.get('display_due_date_field') == 'True')
        display_updated_date_field = (self.request.get('display_updated_date_field') == 'True')
        
        logging.info(fn_name + "Selected format = " + str(export_format))
        # logging.debug(fn_name + "dim_completed_tasks = " + str(dim_completed_tasks))
        # logging.debug(fn_name + "display_completed_date_field = " + str(display_completed_date_field))
        # logging.debug(fn_name + "display_due_date_field = " + str(display_due_date_field))
        # logging.debug(fn_name + "display_updated_date_field = " + str(display_updated_date_field))
        

        # Filename format is "tasks_FORMAT_EMAILADDR_YYYY-MM-DD.EXT"
        # CAUTION: Do not include characters that may not be valid on some filesystems (e.g., colon is not valid on Windows)
        output_filename_base = "tasks_%s_%s_%s" % (export_format, user_email, datetime.datetime.now().strftime("%Y-%m-%d"))
        
        if export_format in ['html1', 'py_nested']:
            logging.debug(fn_name + "Modifying data for " + export_format + " format")
            # Modify structure so that the html1 template can indent tasks
            logging.debug(fn_name + "Building new collection of nested tasks to support indenting")
            for tasklist in tasklists:
                tasks = tasklist[u'tasks']
                
                if len(tasks) > 0: # Non-empty tasklist
                    # Add default metadata to each task, which will be modified in the next round
                    for task in tasks:
                        task[u'children'] = []
                        task[u'depth'] = 0

                    # Find the sub task relationships
                    for task in tasks:
                        id = task['id']
                        for stask in tasks:
                            sid = stask['id']
                            if stask.has_key(u'parent'):
                                if stask[u'parent'] == id:
                                    stask[u'depth'] = task[u'depth'] + 1
                                    # stask is a child of this task
                                    task[u'children'].append(stask)
                                    
                            
                    # Set parent_ to None for root tasks; required by Django recurse tag
                    for task in tasks:
                        depth = task[u'depth']
                        # If not using customdjango, use inline style attribute to indent by this much
                        # e.g., style="padding-left:{{ task.indent }}px"
                        task[u'indent'] = str(depth * settings.TASK_INDENT)
                        if depth == 0:
                            task['parent_'] = None
                        else:
                            task['parent_'] = task['parent']
                            
        if export_format in ['html_raw']:
            logging.debug(fn_name + "Modifying data for " + export_format + " format")
            # Calculate 'depth' and add 'indent' property so that WriteHtmlRaw() can indent tasks
            for tasklist in tasklists:
                tasks = tasklist[u'tasks']
                
                if len(tasks) > 0: # Non-empty tasklist
                    # Add default metadata to each task, which will be modified in the next round
                    for task in tasks:
                        task[u'depth'] = 0

                    # Find the sub task relationships
                    for task in tasks:
                        id = task['id']
                        for stask in tasks:
                            sid = stask['id']
                            if stask.has_key(u'parent'):
                                if stask[u'parent'] == id:
                                    stask[u'depth'] = task[u'depth'] + 1
                                    
                            
                    for task in tasks:
                        depth = task[u'depth']
                        task[u'indent'] = str(depth * settings.TASK_INDENT).strip()
                            
        # # TODO: Fix this, so that we can use the recurse tag in the hTodo template
        # # Currently throws AttributeError: 'dict' object has no attribute 'position'
        # if export_format == 'hTodo':
            # logging.debug(fn_name + "Modifying data for " + export_format + " format")
            # # Use the collection of Task object when using the hTodo Django template
            # # Create structure so that the Django template can recurse tasks
            # logging.debug(fn_name + "Building collection of Task objects for hTodo")
            # list_of_tasklists = []
            # for tasklist in tasks_data.tasklists:
                # list_of_tasks = []
                # tasks = tasklist[u'tasks']
                
                # if len(tasks) > 0: # Non-empty tasklist
                    # # Find the sub task relationships
                    # for task in tasks:
                        # new_task = model.Task(task)
                        # list_of_tasks.append(new_task)
                        
                    # for t in list_of_tasks:    
                        # id = t.id
                        # for st in list_of_tasks:
                            # sid = st.id
                            # if st.parent:
                                # if st.parent == id:
                                    # t.children.append(st)

            # #template_values['tasklists'] = list_of_tasklists
            # tasklists = list_of_tasklists
          
        template_values = {'app_title' : app_title,
                           'host_msg' : host_msg,
                           'home_page_url' : settings.HOME_PAGE_URL,
                           'product_name' : product_name,
                           'tasklists': tasklists,
                           'dim_completed_tasks' : dim_completed_tasks,
                           'display_completed_date_field' : display_completed_date_field,
                           'display_due_date_field' : display_due_date_field,
                           'display_updated_date_field' : display_updated_date_field,
                           'user_email' : user_email, 
                           'now' : datetime.datetime.now(),
                           'job_start_timestamp' : job_start_timestamp,
                           'exportformat' : export_format,
                           'url_discussion_group' : settings.url_discussion_group,
                           'email_discussion_group' : settings.email_discussion_group,
                           'url_issues_page' : settings.url_issues_page,
                           'url_source_code' : settings.url_source_code,
                           'app_version' : appversion.version,
                           'upload_timestamp' : appversion.upload_timestamp}
        
        # template file name format "tasks_template_FORMAT.EXT",
        #   where FORMAT = export_format (e.g., 'outlook')
        #     and EXT = the file type extension (e.g., 'csv')
        if export_format == 'ics':
            self.WriteIcsUsingTemplate(template_values, export_format, output_filename_base)
        elif export_format in ['outlook', 'raw', 'raw1']:
            self.WriteCsvUsingTemplate(template_values, export_format, output_filename_base)
        elif export_format in ['html', 'html1']:
            self.WriteHtmlTemplate(template_values, export_format)
        # elif export_format == 'hTodo':
            # self.WriteHtmlTemplate(template_values, export_format)
        elif export_format == 'RTM':
            self.SendEmailUsingTemplate(template_values, export_format, user_email, output_filename_base)
        elif export_format in ['py', 'py_nested']:
            self.WriteTextUsingTemplate(template_values, export_format, output_filename_base, 'py')
        elif export_format == 'html_raw':
            self.WriteHtmlRaw(template_values)
        else:
            logging.warning(fn_name + "Unsupported export format: %s" % export_format)
            # TODO: Handle invalid export_format nicely - display message to user & go back to main page
            self.response.out.write("<br /><h2>Unsupported export format: %s</h2>" % export_format)
        tasklists = None
        logging.debug(fn_name + "Calling garbage collection")
        gc.collect()
        logging.debug(fn_name + "<End>")
        logservice.flush()

  

    def DisplayErrorPage(self,
                       exc_type, 
                       err_desc = None, 
                       err_details = None,
                       err_msg = None, 
                       app_title = settings.DEFAULT_APP_TITLE,
                       host_msg = None):
        """ Display an error page to the user """
        fn_name = "DisplayErrorPage(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        app_version = None
        app_upload_timestamp = None
           
        if hasattr(appversion, 'version'):
          app_version = appversion.version
          
        if hasattr(appversion, 'upload_timestamp'):
          app_upload_timestamp = appversion.upload_timestamp

        err_template_values = {'app_title' : app_title,
                               'host_msg' : host_msg,
                               'exc_type' : exc_type,
                               'err_desc' : err_desc,
                               'err_details' : err_details,
                               'err_msg' : err_msg,
                               'app_version' : app_version,
                               'app_upload_timestamp' : app_upload_timestamp,
                               'err_datetimestamp' : datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z'),
                               'url_discussion_group' : settings.url_discussion_group,
                               'email_discussion_group' : settings.email_discussion_group,
                               'url_issues_page' : settings.url_issues_page,
                               'url_source_code' : settings.url_source_code}
                                 
        
        # Log and flush before starting operation which may cause memory limit exceeded error
        logging.debug(fn_name + "building template")
        logservice.flush() 
        
        path = os.path.join(os.path.dirname(__file__), "error_message.html")
        logging.debug(fn_name + "Writing error page")
        logging.debug(err_template_values)
        self.response.out.write(template.render(path, err_template_values))
        # logging.debug(fn_name + "Calling garbage collection")
        # gc.collect()
        logging.debug(fn_name + "<End>")
        logservice.flush()

        
    
    def EscapeHtml(self, text):
        """Produce entities within text."""
        if text is None:
            return None
        return cgi.escape(text).encode('ascii', 'xmlcharrefreplace')
        #return "".join(html_escape_table.get(c,c) for c in text)

        
        
    def WriteHtmlRaw(self, template_values):
        """ Manually build an HTML representation of the user's tasks.
        
            This method creates the page manually, in an attempt to reduce the
            amount of memory used when using Django templates to build HTML pages
        """
        
        fn_name = "WriteHtmlRaw() "
        
        user_email = template_values.get('user_email')
        logout_url = template_values.get('logout_url')
        tasklists = template_values.get('tasklists')
        job_start_timestamp = template_values.get('job_start_timestamp')
        dim_completed_tasks = template_values.get('dim_completed_tasks')
        display_completed_date_field = template_values.get('display_completed_date_field')
        display_updated_date_field = template_values.get('display_updated_date_field')
        display_due_date_field = template_values.get('display_due_date_field')
        url_discussion_group = template_values.get('url_discussion_group')
        email_discussion_group = template_values.get('email_discussion_group')
        url_issues_page = template_values.get('url_issues_page')
        url_source_code = template_values.get('url_source_code')
        app_title = template_values.get('app_title')
        app_version = template_values.get('app_version')
        
        self.response.out.write("""<html>
            <head>
                <title>""")
        self.response.out.write(app_title)
        self.response.out.write("""- List of tasks</title>
                <link rel="stylesheet" type="text/css" href="tasks_backup.css"></link>
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
            <body>
            <div class="usertitle">
                Authorised user: """)
        self.response.out.write(user_email)
        self.response.out.write(' <span class="logout-link">[ <a href="')
        self.response.out.write(logout_url)
        self.response.out.write('">Log out</a> ]</span></div>')
            
        num_tasklists = len(tasklists)
        if num_tasklists > 0:
            # Display the job timestamp, so that it is clear when the snapshot was taken
            self.response.out.write("""
                    <div class="break">
                        <h3>Tasks for """)
            self.response.out.write(user_email)
            self.response.out.write(""" as at """)
            self.response.out.write(job_start_timestamp)
            self.response.out.write(""" UTC</h3>
                        <p>""")
            self.response.out.write(num_tasklists)
            self.response.out.write(""" task lists.</p>
                    </div>""")
                    
            for tasklist in tasklists:
                num_tasks = len(tasklist)
                if num_tasks > 0:
                
                    tasklist_title = tasklist.get(u'title')
                    if len(tasklist_title.strip()) == 0:
                        tasklist_title = "<Unnamed Tasklist>"
                    tasklist_title = self.EscapeHtml(tasklist_title)

                    tasks = tasklist.get(u'tasks')
                    num_tasks = len(tasks)
                    self.response.out.write("""
                        <div class="tasklist">
                            <div class="tasklistheading">
                                Task List: """)
                    self.response.out.write(tasklist_title)
                    self.response.out.write(""" - """)
                    self.response.out.write(num_tasks)
                    self.response.out.write(""" tasks.
                            </div>""")
                                        
                    self.response.out.write("""
                        <div class="tasks">""")
                        
                    for task in tasks:
                        task_title = task.get(u'title', "<No Task Title>")
                        if len(task_title.strip()) == 0:
                            task_title = "<Unnamed Task>"
                        task_title = self.EscapeHtml(task_title)
                        
                        task_notes = self.EscapeHtml(task.get(u'notes', None))
                        task_deleted = task.get(u'deleted', None)
                        task_hidden = task.get(u'hidden', None)
                        task_indent = str(task.get('indent', 0))
                        
                        
                        if u'due' in task:
                            task_due = task[u'due'].strftime('%a, %d %b %Y') + " UTC"
                        else:
                            task_due = None
                            
                        if u'updated' in task:
                            task_updated = task[u'updated'].strftime('%H:%M:%S %a, %d %b %Y') + " UTC"
                        else:
                            task_updated = None
                            
                        if u'completed' in task:
                            task_completed = True
                            task_completed_date = task[u'completed'].strftime('%H:%M %a, %d %b %Y') + " UTC"
                            task_status_str = "&#x2713;"
                        else:
                            task_completed = False
                            task_status_str = "[ &nbsp;]"
                        
                        dim_class = ""
                        if task_completed and dim_completed_tasks:
                            dim_class = "dim"
                        if task_deleted or task_hidden:
                            dim_class = "dim"
                        
                        self.response.out.write("""
                            <!-- Task will be dim if; 
                                  task is deleted OR 
                                  task is hidden OR 
                                  task is completed AND user checked dim_completed_tasks
                            -->
                            <div 
                                style="padding-left:""")
                        self.response.out.write(task_indent)
                        self.response.out.write("""px" 
                                class="task-html1 """)
                        self.response.out.write(dim_class)
                        # Note, additional double-quote (4 total), as the class= attribute is 
                        # terminated with a double-quote after the class name
                        self.response.out.write("""" 
                            >
                                <div >
                                    <span class="status-cell">""")
                        self.response.out.write(task_status_str)
                        self.response.out.write("""</span>
                                    <span class="task-title-html1">""")
                        self.response.out.write(task_title)
                        self.response.out.write("""</span>
                                </div>
                                <div class="task-details-html1">""")
                        
                        if task_completed and display_completed_date_field:
                            self.response.out.write("""<div class="task-attribute">
                                    <span class="fieldlabel">COMPLETED:</span> """)
                            self.response.out.write(task_completed_date)
                            self.response.out.write("""</div>""")
                                    
                        if task_notes:
                            self.response.out.write("""<div class="task-notes">""")
                            self.response.out.write(task_notes)
                            self.response.out.write("""</div>""")
                                    
                        if task_due and display_due_date_field:
                            self.response.out.write("""<div class="task-attribute">
                                    <span class="fieldlabel">Due: </span>""")
                            self.response.out.write(task_due)        
                            self.response.out.write("""</div>""")
                                    
                        if task_updated and display_updated_date_field:
                            self.response.out.write("""<div class="task-attribute">
                                    <span class="fieldlabel">Updated:</span> """)
                            self.response.out.write(task_updated)
                            self.response.out.write("""</div>""")
                            
                        if task_deleted:
                            self.response.out.write("""
                                <div class="task-attribute-hidden-or-deleted">- Deleted -</div>
                                """)
                                
                        if task_hidden:
                            self.response.out.write("""
                                <div class="task-attribute-hidden-or-deleted">- Hidden -</div>
                                """)
                                
                        self.response.out.write("""
                                </div>  <!-- End of task details div -->
                            </div> <!-- End of task div -->
                            """)
                            
                    self.response.out.write("""
                            </div> <!-- End of tasks div -->
                        """)
                                           
                else:
                    self.response.out.write("""
                            <div class="tasklistheading">Task List: %s</div>
                                <div class="no-tasks">
                                     No tasks
                            </div>""" % tasklist_title)
                    
            self.response.out.write("""
                    <div class="break">
                        NOTE: Due, Updated and Completed dates and times are UTC, because that is how Google stores them.
                    </div>""")
                    
        else:
            self.response.out.write("""
                <div class="break">
                        <h3>No tasklists found for %s</h3>
                    </div>""" % user_email)

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
        logging.debug(fn_name + "Calling garbage collection")
        gc.collect()
        logging.debug(fn_name + "<End>")
        logservice.flush()
               
        
        
        

    # Potential TODO items (if email quota is sufficient)
    #   TODO: Allow other formats
    #   TODO: Allow attachments (e.g. Outlook CSV) ???
    #   TODO: Improve subject line
    def SendEmailUsingTemplate(self, template_values, export_format, user_email, output_filename_base):
        """ Send an email, formatted according to the specified .txt template file
            Currently supports export_format = 'RTM' (Remember The Milk)
        """
        fn_name = "SendEmailUsingTemplate(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        # if shared.isTestUser(user_email):
          # logging.debug(fn_name + "Creating email body using template")
        # Use a template to convert all the tasks to the desired format 
        template_filename = "tasks_template_%s.txt" % export_format
        
        # Log and flush before starting operation which may cause memory limit exceeded error
        logging.debug(fn_name + "building template")
        logservice.flush() 
        
        path = os.path.join(os.path.dirname(__file__), template_filename)
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
        except Exception, e:
            logging.exception(fn_name + "Unable to send email")
            self.response.out.write("""Unable to send email. 
                Please report the following error to <a href="http://%s">%s</a>
                <br />
                %s
                """ % (settings.url_issues_page, settings.url_issues_page, str(e)))
            logging.debug(fn_name + "<End> (due to exception)")
            return
            
            
        if shared.isTestUser(user_email):
          logging.debug(fn_name + "Email sent to %s" % user_email)
        else:
          logging.debug(fn_name + "Email sent")
          
        self.response.out.write("Email sent to %s </br>Use your browser back button to return to the previous page" % user_email)
        #self.redirect("/completed")
        # logging.debug(fn_name + "Calling garbage collection")
        # gc.collect()
        logging.debug(fn_name + "<End>")
        logservice.flush()


    def WriteIcsUsingTemplate(self, template_values, export_format, output_filename_base):
        """ Write an ICS file according to the specified .ics template file
            Currently supports export_format = 'ics'
        """
        fn_name = "WriteIcsUsingTemplate(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        template_filename = "tasks_template_%s.ics" % export_format
        output_filename = output_filename_base + ".ics"
        self.response.headers["Content-Type"] = "text/calendar"
        self.response.headers.add_header(
            "Content-Disposition", "attachment; filename=%s" % output_filename)

        
        # Log and flush before starting operation which may cause memory limit exceeded error
        logging.debug(fn_name + "building template")
        logservice.flush() 
        
        path = os.path.join(os.path.dirname(__file__), template_filename)
        if shared.isTestUser(template_values['user_email']):
          logging.debug(fn_name + "Writing %s format to %s" % (export_format, output_filename))
        else:
          logging.debug(fn_name + "Writing %s format" % export_format)
        self.response.out.write(template.render(path, template_values))
        # logging.debug(fn_name + "Calling garbage collection")
        # gc.collect()
        logging.debug(fn_name + "<End>")
        logservice.flush()
        

    def WriteCsvUsingTemplate(self, template_values, export_format, output_filename_base):
        """ Write a CSV file according to the specified .csv template file
            Currently supports export_format = 'outlook', 'raw' and 'raw1'
        """
        fn_name = "WriteCsvUsingTemplate(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        template_filename = "tasks_template_%s.csv" % export_format
        output_filename = output_filename_base + ".csv"
        self.response.headers["Content-Type"] = "text/csv"
        self.response.headers.add_header(
            "Content-Disposition", "attachment; filename=%s" % output_filename)

        
        # Log and flush before starting operation which may cause memory limit exceeded error
        logging.debug(fn_name + "building template")
        logservice.flush() 
        
        path = os.path.join(os.path.dirname(__file__), template_filename)
        if shared.isTestUser(template_values['user_email']):
          logging.debug(fn_name + "Writing %s format to %s" % (export_format, output_filename))
        else:
          logging.debug(fn_name + "Writing %s format" % export_format)
        self.response.out.write(template.render(path, template_values))
        # logging.debug(fn_name + "Calling garbage collection")
        # gc.collect()
        logging.debug(fn_name + "<End>")
        logservice.flush()


    def WriteTextUsingTemplate(self, template_values, export_format, output_filename_base, file_extension):
        """ Write a TXT file according to the specified .txt template file
            Currently supports export_format = 'py' and 'py_nested' 
        """
        fn_name = "WriteTextUsingTemplate(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        template_filename = "tasks_template_%s.%s" % (export_format, file_extension)
        output_filename = output_filename_base + "." + file_extension
        self.response.headers["Content-Type"] = "text/plain"
        self.response.headers.add_header(
            "Content-Disposition", "attachment;filename=%s" % output_filename)

        
        # Log and flush before starting operation which may cause memory limit exceeded error
        logging.debug(fn_name + "building template")
        logservice.flush() 
        
        path = os.path.join(os.path.dirname(__file__), template_filename)
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


    def WriteHtmlTemplate(self, template_values, export_format):
        """ Write an HTML page according to the specified .html template file
            Currently supports export_format = 'html'
        """
        fn_name = "WriteHtmlTemplate(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        logging.debug(fn_name + "dim_completed_tasks = " + str(template_values['dim_completed_tasks']))
        logging.debug(fn_name + "display_completed_date_field = " + str(template_values['display_completed_date_field']))
        logging.debug(fn_name + "display_due_date_field = " + str(template_values['display_due_date_field']))
        logging.debug(fn_name + "display_updated_date_field = " + str(template_values['display_updated_date_field']))
        
        template_filename = "tasks_template_%s.html" % export_format
        
        # Log and flush before starting operation which may cause memory limit exceeded error
        logging.debug(fn_name + "building template")
        logservice.flush() 
        
        path = os.path.join(os.path.dirname(__file__), template_filename)
        logging.debug(fn_name + "Writing %s format" % export_format)
        
        # logging.debug(fn_name + "len of template_values = " + str(len(str(template_values))))
        # logservice.flush()
        
        logging.debug(fn_name + "rendering template")
        logservice.flush() 
        
        rendered_page = template.render(path, template_values)
        # logging.debug(fn_name + "len of rendered_page = " + str(len(str(rendered_page))))
        # logservice.flush()
        
        logging.debug(fn_name + "writing response")
        logservice.flush() 
        self.response.out.write(rendered_page)
        #self.response.out.write(str(template_values))
        
        # logging.debug(fn_name + "Calling garbage collection")
        # gc.collect()
        logging.debug(fn_name + "<End>")
        logservice.flush()


    def WriteDebugHtmlTemplate(self, 
                             debugmessages, 
                             datadump1, 
                             datadump2, 
                             datadump3, 
                             datadump4, 
                             app_title = settings.DEFAULT_APP_TITLE, 
                             host_msg = None):
        fn_name = "WriteDebugHtmlTemplate(): "                       
        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        # Log and flush before starting operation which may cause memory limit exceeded error
        logging.debug(fn_name + "building template")
        logservice.flush() 
        
        debug_template_values = {'debug_version' : datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                                 'debugmessages': debugmessages,
                                 'datadump1': datadump1,
                                 'datadump2': datadump2,
                                 'datadump3': datadump3,
                                 'datadump4': datadump4,
                                 'url_discussion_group' : settings.url_discussion_group,
                                 'email_discussion_group' : settings.email_discussion_group,
                                 'url_issues_page' : settings.url_issues_page,
                                 'url_source_code' : settings.url_source_code,
                                 'app_title' : app_title,
                                 'host_msg' : host_msg}
        path = os.path.join(os.path.dirname(__file__), 'debug_template.html')
        logging.debug(fn_name + "Writing debug HTML")
        self.response.out.write(template.render(path, debug_template_values))
        # logging.debug(fn_name + "Calling garbage collection")
        # gc.collect()
        logging.debug(fn_name + "<End>")
        logservice.flush()


class OAuthHandler(webapp.RequestHandler):
    """Handler for /oauth2callback."""

    def get(self):
        """Handles GET requests for /oauth2callback."""
        fn_name = "OAuthHandler.get() "
        
        if not self.request.get("code"):
            logging.info(fn_name + "No 'code', so redirecting to /")
            logservice.flush()
            self.redirect("/")
            return
        user = users.get_current_user()
        logging.debug(fn_name + "Retrieving flow for " + str(user.user_id()))
        flow = pickle.loads(memcache.get(user.user_id()))
        if flow:
            logging.debug(fn_name + "Got flow. Retrieving credentials for " + str(self.request.params))
            error = False
            try:
                credentials = flow.step2_exchange(self.request.params)
            except client.FlowExchangeError, e:
                logging.exception(fn_name + "FlowExchangeError")
                credentials = None
                error = True
            except Exception, e:
                logging.exception(fn_name + "Redirecting to " + settings.INVALID_CREDENTIALS_URL)
                logservice.flush()
                self.redirect(settings.INVALID_CREDENTIALS_URL)
                return
            appengine.StorageByKeyName(
                model.Credentials, user.user_id(), "credentials").put(credentials)
            if error:
                logging.warning(fn_name + "FlowExchangeError, redirecting to '/?msg=ACCOUNT_ERROR'")
                logservice.flush()
                self.redirect("/?msg=ACCOUNT_ERROR")
            else:
                logging.debug(fn_name + "Retrieved credentials ==>")
                shared.DumpObj(credentials)
                logservice.flush()
                
                if not credentials:
                    logging.debug(fn_name + "No credentials. Redirecting to " + settings.INVALID_CREDENTIALS_URL)
                    logging.debug(fn_name + "user ==>")
                    shared.DumpObj(user)
                    logservice.flush()
                    self.redirect(settings.INVALID_CREDENTIALS_URL)
                elif credentials.invalid:
                    logging.warning(fn_name + "Invalid credentials. Redirecting to " + settings.INVALID_CREDENTIALS_URL)
                    logging.debug(fn_name + "user ==>")
                    shared.DumpObj(user)
                    logging.debug(fn_name + "credentials ==>")
                    shared.DumpObj(credentials)
                    logservice.flush()
                    self.redirect(settings.INVALID_CREDENTIALS_URL)
                else:
                    logging.debug(fn_name + "Credentials valid. Redirecting to " + str(self.request.get("state")))
                    logservice.flush()
                    self.redirect(self.request.get("state"))

        
def real_main():
    logging.info("main(): Starting tasks-backup (app version %s)" %appversion.version)
    template.register_template_library("common.customdjango")

    application = webapp.WSGIApplication(
        [
            (settings.HOME_PAGE_URL,            MainHandler),
            ("/completed",                      CompletedHandler),
            ("/auth",                           AuthRedirectHandler),
            (settings.RESULTS_URL,              ReturnResultsHandler),
            (settings.START_BACKUP_URL,         StartBackupHandler),
            (settings.PROGRESS_URL,             ShowProgressHandler),
            (settings.INVALID_CREDENTIALS_URL,  InvalidCredentialsHandler),
            ("/oauth2callback",                 OAuthHandler),
        ], debug=False)
    util.run_wsgi_app(application)
    logging.info("main(): <End>")

def profile_main():
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
    
main = real_main

if __name__ == "__main__":
    main()

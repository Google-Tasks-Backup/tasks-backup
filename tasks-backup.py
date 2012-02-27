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
#import urllib

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

  
  
  
  

class MainHandler(webapp.RequestHandler):
    """Handler for /."""

    def get(self):
        """Handles GET requests for /."""

        fn_name = "MainHandler.get(): "

        logging.debug(fn_name + "<Start>")

        client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)

          
        user, credentials = _GetCredentials()
        if user:
            user_email = user.email()
        path = os.path.join(os.path.dirname(__file__), "index.html")
        if not credentials or credentials.invalid:
            is_authorized = False
        else:
            is_authorized = True

        if shared.isTestUser(user_email):
            logging.debug(fn_name + "Started by test user %s" % user_email)
          
        template_values = {'app_title' : app_title,
                           'host_msg' : host_msg,
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
        logging.debug(fn_name + "<End> (app version %s)" %appversion.version )
    

class AuthRedirectHandler(webapp.RequestHandler):
  """Handler for /auth."""

  def get(self):
    """Handles GET requests for /auth."""
    user, credentials = _GetCredentials()

    if not credentials or credentials.invalid:
      _RedirectForOAuth(self, user)
    else:
      self.redirect("/")

      
    
class CompletedHandler(webapp.RequestHandler):
    """Handler for /completed."""

    def get(self):
        """Handles GET requests for /completed"""
        fn_name = "CompletedHandler.get(): "

        user, credentials = _GetCredentials()
        user_email = user.email()
        if isUserEmail(user_email):
            logging.debug(fn_name + "user_email = [%s]" % user_email)

        client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)

        path = os.path.join(os.path.dirname(__file__), "completed.html")
        if not credentials or credentials.invalid:
            is_authorized = False
        else:
            is_authorized = True
            
        template_values = {'app_title' : app_title,
                             'host_msg' : host_msg,
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
       
        logging.debug(fn_name + "<start>")

        # client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)
        
        user, credentials = _GetCredentials()
        
        # TODO: Handle unauthenticated user
        if user is None:
            logging.info(fn_name + "user is None, redirecting to /")
            self.redirect('/')
            
        user_email = user.email()
        is_test_user = shared.isTestUser(user_email)
        
        if is_test_user:
          logging.debug(fn_name + "POST args: include_hidden = " + str(self.request.get('include_hidden')) +
                            ", include_completed = " + str(self.request.get('include_completed')) +
                            ", include_deleted = " + str(self.request.get('include_deleted')))
                            
        logging.debug(fn_name + "Storing details for " + str(user_email))
        
  
        # Create a DB record, using the user's email address as the key
        tasks_backup_job = model.TasksBackupJob(key_name=user_email)
        tasks_backup_job.include_completed = (self.request.get('include_completed') == 'True')
        tasks_backup_job.include_deleted = (self.request.get('include_deleted') == 'True')
        tasks_backup_job.include_hidden = (self.request.get('include_hidden') == 'True')
        tasks_backup_job.user = user
        tasks_backup_job.credentials = credentials
        tasks_backup_job.put()

        if is_test_user:
            logging.debug(fn_name + "tasks_backup_job.include_hidden = " + str(tasks_backup_job.include_hidden) +
                                    ", tasks_backup_job.include_completed = " + str(tasks_backup_job.include_completed) +
                                    ", tasks_backup_job.include_deleted = " + str(tasks_backup_job.include_deleted))

        # Add the task to the taskqueue
        # Add the request to the tasks queue, passing in the user's email so that the task can access the
        # databse record
        q = taskqueue.Queue(settings.BACKUP_REQUEST_QUEUE_NAME)
        t = taskqueue.Task(url='/worker', params={settings.TASKS_QUEUE_KEY_NAME : user_email}, method='POST')
        logging.info(fn_name + "Adding task to " + str(settings.BACKUP_REQUEST_QUEUE_NAME) + 
            " queue, for " + str(user_email))
        try:
            q.add(t)
        except exception, e:
            logging.exception(fn_name + "Exception adding task to taskqueue. Redirecting to " + str(settings.PROGRESS_URL))
            self.redirect(settings.PROGRESS_URL + "?msg=Exception%20adding%20task%20to%20taskqueue")
            return

        logging.debug(fn_name + "Redirect to " + settings.PROGRESS_URL + " for " + str(user_email))
        logging.debug(fn_name + "<End> for " + str(user_email))
        self.redirect(settings.PROGRESS_URL)

        
class ShowProgressHandler(webapp.RequestHandler):
    """Handler to display progress to the user """
    
    def get(self):
        # TODO: Display the progress page, which includes a refresh meta-tag to recall this page every n seconds
        fn_name = "ShowProgressHandler.get(): "
    
        logging.debug(fn_name + "<Start>")
        
        client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)
      
          
        user, credentials = _GetCredentials()
        if not credentials or credentials.invalid:
            # TODO: Handle unauthenticated user
            is_authorized = False
            # logging.debug(fn_name + "is_authorized = False")
        else:
            is_authorized = True
        
        
        # TODO: Handle unauthenticated user
        if user is None:
            logging.error(fn_name + "user is None, redirecting to /")
            self.redirect('/')
            return
            
        user_email = user.email()
        
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
                        " seconds ago at " + str(job_start_timestamp))
                    error_message = "Job appears to have stalled. Status was " + tasks_backup_job.status
                    if tasks_backup_job.error_message:
                        error_message = error_message + ", previous error was " + tasks_backup_job.error_message
                    status = 'job_stalled'
                    
        logging.debug(fn_name + "Status = " + str(status) + ", progress = " + str(progress) + 
            " for " + str(user_email) + ", started at " + str(job_start_timestamp))
        
        if error_message:
            logging.warning(fn_name + "Error message: " + str(error_message))
            
        path = os.path.join(os.path.dirname(__file__), "progress.html")
        
        #refresh_url = self.request.host + '/' + settings.PROGRESS_URL
        
        template_values = {'app_title' : app_title,
                           'host_msg' : host_msg,
                           'product_name' : product_name,
                           'status' : status,
                           'progress' : progress,
                           'error_message' : error_message,
                           'job_start_timestamp' : job_start_timestamp,
                           'is_authorized': is_authorized,
                           'refresh_interval' : settings.PROGRESS_PAGE_REFRESH_INTERVAL,
                           'user_email' : user_email,
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
        logging.debug(fn_name + "<End>")
        
          
class ReturnResultsHandler(webapp.RequestHandler):
    """Handler to return results to user in the requested format """
    
    def get(self):
        # """ Display the page to allow user to choose format for results """
        fn_name = "ReturnResultsHandler.get(): "
        logging.warning(fn_name + "Expected POST. Calling post handler")
        self.post()
        
        # # TODO: Redirect user to page to start a backup
        # logging.warning(fn_name + "TODO - doing nothing")
        # self.response.out.write("TODO - doing nothing")
        
    def post(self):
        """ Return results to the user """
        fn_name = "ReturnResultsHandler.post(): "
        
        logging.debug(fn_name + "<Start>")
        
        client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)
        
        user, credentials = _GetCredentials()
        user_email = user.email()
        is_test_user = shared.isTestUser(user_email)
        
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
        
        logging.info(fn_name + "Selected format = " + str(export_format))
        

        # Filename format is "tasks_FORMAT_EMAILADDR_YYYY-MM-DD.EXT"
        # CAUTION: Do not include characters that may not be valid on some filesystems (e.g., colon is not valid on Windows)
        output_filename_base = "tasks_%s_%s_%s" % (export_format, user_email, datetime.datetime.now().strftime("%Y-%m-%d"))
        
        template_values = {'app_title' : app_title,
                           'host_msg' : host_msg,
                           'product_name' : product_name,
                           'tasklists': tasklists,
                           'user_email' : user_email, 
                           'now' : datetime.datetime.now(),
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
        elif export_format == 'outlook' or export_format == 'raw':
            self.WriteCsvUsingTemplate(template_values, export_format, output_filename_base)
        elif export_format == 'html':
            self.WriteHtmlTemplate(template_values, export_format)
        elif export_format == 'hTodo':
            self.WriteHtmlTemplate(template_values, export_format)
        elif export_format == 'RTM':
            self.SendEmailUsingTemplate(template_values, export_format, user_email, output_filename_base)
        else:
            logging.warning(fn_name + "Unsupported export format: %s" % export_format)
            # TODO: Handle invalid export_format nicely - display message to user & go back to main page
            self.response.out.write("<br /><h2>Unsupported export format: %s</h2>" % export_format)

        logging.debug(fn_name + "<end>")

  
  

    def DisplayErrorPage(self,
                       exc_type, 
                       err_desc = None, 
                       err_details = None,
                       err_msg = None, 
                       app_title = settings.DEFAULT_APP_TITLE,
                       host_msg = None):
        """ Display an error page to the user """
        fn_name = "DisplayErrorPage(): "

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
                                 
        path = os.path.join(os.path.dirname(__file__), "error_message.html")
        logging.debug(fn_name + "Writing error page")
        logging.debug(err_template_values)
        self.response.out.write(template.render(path, err_template_values))



    # Potential TODO items (if email quota is sufficient)
    #   TODO: Allow other formats
    #   TODO: Allow attachments (e.g. Outlook CSV) ???
    #   TODO: Improve subject line
    def SendEmailUsingTemplate(self, template_values, export_format, user_email, output_filename_base):
        """ Send an email, formatted according to the specified .txt template file
            Currently supports export_format = 'RTM' (Remember The Milk)
        """
        fn_name = "SendEmailUsingTemplate(): "

        # if shared.isTestUser(user_email):
          # logging.debug(fn_name + "Creating email body using template")
        # Use a template to convert all the tasks to the desired format 
        template_filename = "tasks_template_%s.txt" % export_format
        path = os.path.join(os.path.dirname(__file__), template_filename)
        email_body = template.render(path, template_values)

        # if shared.isTestUser(user_email):
          # logging.debug(fn_name + "Sending email")
        # TODO: Catch exception sending & display to user ??
        # According to "C:\Program Files\Google\google_appengine\google\appengine\api\mail.py", 
        #   end_mail() doesn't return any value, but can throw InvalidEmailError when invalid email address provided
        mail.send_mail(sender=user_email,
                       to=user_email,
                       subject=output_filename_base,
                       body=email_body)

        if shared.isTestUser(user_email):
          logging.debug(fn_name + "Email sent to %s" % user_email)
        else:
          logging.debug(fn_name + "Email sent")
          
        self.response.out.write("Email sent to %s </br>Use your browser back button to return to the previous page" % user_email)
        #self.redirect("/completed")


    def WriteIcsUsingTemplate(self, template_values, export_format, output_filename_base):
        """ Write an ICS file according to the specified .ics template file
            Currently supports export_format = 'ics'
        """
        fn_name = "WriteIcsUsingTemplate(): "

        template_filename = "tasks_template_%s.ics" % export_format
        output_filename = output_filename_base + ".ics"
        self.response.headers["Content-Type"] = "text/calendar"
        self.response.headers.add_header(
            "Content-Disposition", "attachment; filename=%s" % output_filename)

        path = os.path.join(os.path.dirname(__file__), template_filename)
        if shared.isTestUser(template_values['user_email']):
          logging.debug(fn_name + "Writing %s format to %s" % (export_format, output_filename))
        else:
          logging.debug(fn_name + "Writing %s format" % export_format)
        self.response.out.write(template.render(path, template_values))


    def WriteCsvUsingTemplate(self, template_values, export_format, output_filename_base):
        """ Write a CSV file according to the specified .csv template file
            Currently supports export_format = 'outlook' 
        """
        fn_name = "WriteCsvUsingTemplate(): "

        template_filename = "tasks_template_%s.csv" % export_format
        output_filename = output_filename_base + ".csv"
        self.response.headers["Content-Type"] = "text/csv"
        self.response.headers.add_header(
            "Content-Disposition", "attachment; filename=%s" % output_filename)

        path = os.path.join(os.path.dirname(__file__), template_filename)
        if shared.isTestUser(template_values['user_email']):
          logging.debug(fn_name + "Writing %s format to %s" % (export_format, output_filename))
        else:
          logging.debug(fn_name + "Writing %s format" % export_format)
        self.response.out.write(template.render(path, template_values))


    def WriteHtmlTemplate(self, template_values, export_format):
        """ Write an HTML page according to the specified .html template file
            Currently supports export_format = 'html' and 'hTodo'
        """
        fn_name = "WriteHtmlTemplate(): "

        template_filename = "tasks_template_%s.html" % export_format
        path = os.path.join(os.path.dirname(__file__), template_filename)
        logging.debug(fn_name + "Writing %s format" % export_format)
        self.response.out.write(template.render(path, template_values))


    def WriteDebugHtmlTemplate(self, 
                             debugmessages, 
                             datadump1, 
                             datadump2, 
                             datadump3, 
                             datadump4, 
                             app_title = settings.DEFAULT_APP_TITLE, 
                             host_msg = None):
        fn_name = "WriteDebugHtmlTemplate(): "                       
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

 
                                 

class OAuthHandler(webapp.RequestHandler):
    """Handler for /oauth2callback."""

    def get(self):
        """Handles GET requests for /oauth2callback."""
        if not self.request.get("code"):
            self.redirect("/")
            return
        user = users.get_current_user()
        flow = pickle.loads(memcache.get(user.user_id()))
        if flow:
            error = False
            try:
                credentials = flow.step2_exchange(self.request.params)
            except client.FlowExchangeError, e:
                credentials = None
                error = True
            appengine.StorageByKeyName(
                model.Credentials, user.user_id(), "credentials").put(credentials)
            if error:
                self.redirect("/?msg=ACCOUNT_ERROR")
            else:
                self.redirect(self.request.get("state"))

        

def main():
    logging.info("Starting tasks-backup")
    template.register_template_library("common.customdjango")

    application = webapp.WSGIApplication(
        [
            ("/",                         MainHandler),
            ("/completed",                CompletedHandler),
            ("/auth",                     AuthRedirectHandler),
            (settings.RESULTS_URL,        ReturnResultsHandler),
            (settings.START_BACKUP_URL,   StartBackupHandler),
            (settings.PROGRESS_URL,       ShowProgressHandler),
            ("/oauth2callback",           OAuthHandler),
        ], debug=True)
    util.run_wsgi_app(application)

if __name__ == "__main__":
    main()

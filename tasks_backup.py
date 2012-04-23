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
from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers

logservice.AUTOFLUSH_EVERY_SECONDS = 5
logservice.AUTOFLUSH_EVERY_BYTES = None
logservice.AUTOFLUSH_EVERY_LINES = 5
logservice.AUTOFLUSH_ENABLED = True

import httplib2
import Cookie

import model
import settings
import datetime
from datetime import timedelta
import appversion # appversion.version is set before the upload process to keep the version number consistent
import shared # Code whis is common between tasks-backup.py and worker.py

# Name of folder containg templates. Do not include path separator characters, as they are inserted by os.path.join()
_path_to_templates = "templates"

def _set_cookie(res, key, value='', max_age=None,
                   path='/', domain=None, secure=None, httponly=False,
                   version=None, comment=None):
    """
    Set (add) a cookie for the response
    """       
    cookies = Cookie.SimpleCookie()
    cookies[key] = value
    for var_name, var_value in [
        ('max-age', max_age),
        ('path', path),
        ('domain', domain),
        ('secure', secure),
        ('HttpOnly', httponly),
        ('version', version),
        ('comment', comment),
        ]:
        if var_value is not None and var_value is not False:
            cookies[key][var_name] = str(var_value)
        if max_age is not None:
            cookies[key]['expires'] = max_age
    header_value = cookies[key].output(header='').lstrip()
    res.headers.add_header("Set-Cookie", header_value)
        
  
def _RedirectForOAuth(self, user):
    """Redirects the webapp response to authenticate the user with OAuth2."""

    fn_name = "_RedirectForOAuth(): "
    
    try:
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
        logging.debug(fn_name + "Redirecting to " + str(authorize_url))
        if self.request.cookies.has_key('auth_count'):
            auth_count = int(self.request.cookies['auth_count'])
        else:
            auth_count = 0
        auth_count_str = str(auth_count + 1)
        logging.debug(fn_name + "Writing cookie: auth_count = " + auth_count_str)
        logservice.flush()
        _set_cookie(self.response, 'auth_count', auth_count_str, max_age=120)        

        self.redirect(authorize_url)
    except Exception, e:
        logging.exception(fn_name + "Caught top-level exception")
        self.response.out.write("""Sorry, something went terribly wrong.<br />%s<br />Please report this error to <a href="http://code.google.com/p/tasks-backup/issues/list">code.google.com/p/tasks-backup/issues/list</a>""" % str(e))
        logging.debug(fn_name + "<End> due to exception" )
        logservice.flush()

  
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

  
def _serveRetryPage(self, msg):
    """ Serve retry.html page to user with message, and a Back button """
    fn_name = "_serveRetryPage: "

    logging.debug(fn_name + "<Start>")
    logservice.flush()
    
    try:
        client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)

        logging.debug(fn_name + "Calling _GetCredentials()")
        user, credentials = _GetCredentials()
            
        if user:
            user_email = user.email()
        
        
        path = os.path.join(os.path.dirname(__file__), _path_to_templates, "retry.html")
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
                           'start_backup_url' : settings.START_BACKUP_URL,
                           'msg': msg,
                           'logout_url': users.create_logout_url('/'),
                           'url_discussion_group' : settings.url_discussion_group,
                           'email_discussion_group' : settings.email_discussion_group,
                           'url_issues_page' : settings.url_issues_page,
                           'url_source_code' : settings.url_source_code,
                           'app_version' : appversion.version,
                           'upload_timestamp' : appversion.upload_timestamp}
        self.response.out.write(template.render(path, template_values))
        logging.debug(fn_name + "<End>" )
        logservice.flush()
    except Exception, e:
        logging.exception(fn_name + "Caught top-level exception")
        self.response.out.write("""Sorry, something went terribly wrong.<br />%s<br />Please report this error to <a href="http://code.google.com/p/tasks-backup/issues/list">code.google.com/p/tasks-backup/issues/list</a>""" % str(e))
        logging.debug(fn_name + "<End> due to exception" )
        logservice.flush()
    

class GetNewBlobstoreUrlHandler(webapp.RequestHandler):
    """ Provides a new Blobstore URL. 
        This is used when the user submits a file from an HTML form.
        We don't fill in a Blobstore URL when we build the page, because the URL can expire.
        
        Google provides a unique URL to allow the user to upload the contents of large files. 
        The file contents are then accessible to the applicion through a unique Blobstore key.
    """
    
    def get(self):
        """ Return a new Blobstore URL, as a string """
        upload_url = blobstore.create_upload_url(settings.BLOBSTORE_UPLOAD_URL)
        self.response.out.write(upload_url)


class BlobstoreUploadHandler(blobstore_handlers.BlobstoreUploadHandler):
    def post(self):
        fn_name = "BlobstoreUploadHandler.post(): "
        
        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        try:
            client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)

            logging.debug(fn_name + "Calling _GetCredentials()")
            user, credentials = _GetCredentials()
                
            if user:
                user_email = user.email()
            
            upload_files = self.get_uploads('file') # 'file' is the name of the file upload field in the form
            if upload_files:
                blob_info = upload_files[0]
                logging.debug(fn_name + "key = " + str(blob_info.key()) + ", filename = " + str(blob_info.filename) +
                    ", for " + str(user_email))
                logservice.flush()
                
                # Create a Taskqueue entry to start the import
                
                # Create a DB record, using the user's email address as the key
                tasks_backup_job = model.ProcessTasksJob(key_name=user_email)
                tasks_backup_job.job_type = 'import'
                tasks_backup_job.blobstore_key = str(blob_info.key())
                tasks_backup_job.user = user
                tasks_backup_job.credentials = credentials
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
                    logging.exception(fn_name + "Exception adding task to taskqueue. Redirecting to " + str(settings.PROGRESS_URL))
                    logservice.flush()
                    self.redirect(settings.PROGRESS_URL + "?msg=Exception%20adding%20task%20to%20taskqueue")
                    return

                logging.debug(fn_name + "Redirect to " + settings.PROGRESS_URL + " for " + str(user_email))
                logservice.flush()
                self.redirect(settings.PROGRESS_URL)
                
                # Redirect to Progress page
                self.redirect(settings.PROGRESS_URL)
            else:
                _serveRetryPage(self, 'No file uploaded, please try again.')
            logging.debug(fn_name + "<End>" )
            logservice.flush()
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            self.response.out.write("""Sorry, something went terribly wrong.<br />%s<br />Please report this error to <a href="http://code.google.com/p/tasks-backup/issues/list">code.google.com/p/tasks-backup/issues/list</a>""" % str(e))
            logging.debug(fn_name + "<End> due to exception" )
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
            if self.request.cookies.has_key('auth_count'):
                logging.debug(fn_name + "Cookie: auth_count = " + str(self.request.cookies['auth_count']))
            else:
                logging.debug(fn_name + "No auth_count cookie found")
            logservice.flush()            
                
            client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)
            
            path = os.path.join(os.path.dirname(__file__), _path_to_templates, "invalid_credentials.html")

            template_values = {  'app_title' : app_title,
                                 'app_version' : appversion.version,
                                 'upload_timestamp' : appversion.upload_timestamp,
                                 'rc' : self.request.get('rc'),
                                 'nr' : self.request.get('nr'),
                                 'err' : self.request.get('err'),
                                 'host_msg' : host_msg,
                                 'home_page_url' : settings.HOME_PAGE_URL,
                                 'product_name' : product_name,
                                 'url_discussion_group' : settings.url_discussion_group,
                                 'email_discussion_group' : settings.email_discussion_group,
                                 'url_issues_page' : settings.url_issues_page,
                                 'url_source_code' : settings.url_source_code,
                                 'logout_url': users.create_logout_url('/')}
                         
            self.response.out.write(template.render(path, template_values))
            logging.debug(fn_name + "Writing cookie: Resetting auth_count cookie to zero")
            _set_cookie(self.response, 'auth_count', '0', max_age=120)
            logging.debug(fn_name + "<End>")
            logservice.flush()
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            self.response.out.write("""Sorry, something went terribly wrong.<br />%s<br />Please report this error to <a href="http://code.google.com/p/tasks-backup/issues/list">code.google.com/p/tasks-backup/issues/list</a>""" % str(e))
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()
        
        
class MainHandler(webapp.RequestHandler):
    """Handler for /."""

    def get(self):
        """Handles GET requests for /."""

        fn_name = "MainHandler.get(): "

        logging.debug(fn_name + "<Start> (app version %s)" %appversion.version )
        logservice.flush()
        
        try:
            # DEBUG
            if self.request.cookies.has_key('auth_count'):
                logging.debug(fn_name + "Cookie: auth_count = " + str(self.request.cookies['auth_count']))
            else:
                logging.debug(fn_name + "No auth_count cookie found")
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
                    
            path = os.path.join(os.path.dirname(__file__), _path_to_templates, "index.html")
            if not credentials or credentials.invalid:
                is_authorized = False
            else:
                is_authorized = True
                logging.debug(fn_name + "Resetting auth_count cookie to zero")
                logservice.flush()
                _set_cookie(self.response, 'auth_count', '0', max_age=120)
                if self.request.host in settings.LIMITED_ACCESS_SERVERS:
                    logging.debug(fn_name + "Running on limited-access server")
                    if not shared.isTestUser(user_email):
                        logging.info(fn_name + "Rejecting non-test user on limited access server")
                        self.response.out.write("<h2>This is a test server. Access is limited to test users.</h2>")
                        logging.debug(fn_name + "<End> (restricted access)" )
                        logservice.flush()
                        return

              
            template_values = {'app_title' : app_title,
                               'host_msg' : host_msg,
                               'home_page_url' : settings.HOME_PAGE_URL,
                               'new_blobstore_url' : settings.GET_NEW_BLOBSTORE_URL,
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
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            self.response.out.write("""Sorry, something went terribly wrong.<br />%s<br />Please report this error to <a href="http://code.google.com/p/tasks-backup/issues/list">code.google.com/p/tasks-backup/issues/list</a>""" % str(e))
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()
    

class AuthRedirectHandler(webapp.RequestHandler):
    """Handler for /auth."""

    def get(self):
        """Handles GET requests for /auth."""
        fn_name = "AuthRedirectHandler.get() "
        
        logging.debug(fn_name + "<Start>" )
        logservice.flush()
        
        try:
            # DEBUG
            # if self.request.cookies.has_key('auth_count'):
                # logging.debug(fn_name + "Cookie: auth_count = " + str(self.request.cookies['auth_count']))
            # else:
                # logging.debug(fn_name + "No auth_count cookie found")
            # logservice.flush()            
                
            # Check how many times this has been called (without any other pages having been served)
            if self.request.cookies.has_key('auth_count'):
                auth_count = int(self.request.cookies['auth_count'])
                logging.debug(fn_name + "auth_count = " + str(auth_count))
            else:
                logging.debug(fn_name + "No auth_count cookie found")
                auth_count = 0
                
            user, credentials = _GetCredentials()

            if not credentials: 
                if auth_count > settings.MAX_NUM_AUTH_REQUESTS:
                    # Redirect to Invalid Credentials page
                    logging.warning(fn_name + "credentials is None after " + str(auth_count) + " retries, redirecting to " + 
                        settings.INVALID_CREDENTIALS_URL)
                    self.redirect(settings.INVALID_CREDENTIALS_URL + "?rc=NC&nr=" + str(auth_count))
                else:
                    # Try to authenticate (again)
                    logging.debug(fn_name + "credentials is None, calling _RedirectForOAuth()")
                    _RedirectForOAuth(self, user)
            elif credentials.invalid:
                if auth_count > settings.MAX_NUM_AUTH_REQUESTS:
                    # Redirect to Invalid Credentials page
                    logging.warning(fn_name + "credentials invalid after " + str(auth_count) + " retries, redirecting to " + 
                        settings.INVALID_CREDENTIALS_URL)
                    self.redirect(settings.INVALID_CREDENTIALS_URL + "?rc=IC&nr=" + str(auth_count))
                else:
                    # Try to authenticate (again)
                    logging.debug(fn_name + "credentials invalid, calling _RedirectForOAuth()")
                    _RedirectForOAuth(self, user)
            else:
                logging.debug(fn_name + "Redirecting to /")
                self.redirect("/")
            logging.debug(fn_name + "<End>" )
            logservice.flush()
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            self.response.out.write("""Sorry, something went terribly wrong.<br />%s<br />Please report this error to <a href="http://code.google.com/p/tasks-backup/issues/list">code.google.com/p/tasks-backup/issues/list</a>""" % str(e))
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
            if self.request.cookies.has_key('auth_count'):
                logging.debug(fn_name + "Cookie: auth_count = " + str(self.request.cookies['auth_count']))
            else:
                logging.debug(fn_name + "No auth_count cookie found")
            logservice.flush()            
                
            user, credentials = _GetCredentials()
            # if user is None:
                # logging.warning(fn_name + "user is None, redirecting to " +
                    # settings.INVALID_CREDENTIALS_URL)
                # self.redirect(settings.INVALID_CREDENTIALS_URL + "?rc=NU")
                # return
                
            # if credentials is None or credentials.invalid:
                # logging.warning(fn_name + "credentials is None or invalid, redirecting to " + 
                    # settings.INVALID_CREDENTIALS_URL)
                # self.redirect(settings.INVALID_CREDENTIALS_URL + "?rc=XC")
                # return
                
            user_email = user.email()
            if isUserEmail(user_email):
                logging.debug(fn_name + "user_email = [%s]" % user_email)

            client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)

            path = os.path.join(os.path.dirname(__file__), _path_to_templates, "completed.html")
            if not credentials or credentials.invalid:
                is_authorized = False
            else:
                is_authorized = True
                logging.debug(fn_name + "Resetting auth_count cookie to zero")
                logservice.flush()
                _set_cookie(self.response, 'auth_count', '0', max_age=120)
                
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
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            self.response.out.write("""Sorry, something went terribly wrong.<br />%s<br />Please report this error to <a href="http://code.google.com/p/tasks-backup/issues/list">code.google.com/p/tasks-backup/issues/list</a>""" % str(e))
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()

      
class StartBackupHandler(webapp.RequestHandler):
    """ Handler to start the backup process. """
    
  
    def post(self):
        """ Handles GET request to settings.START_BACKUP_URL, which starts the backup process. """
        
        fn_name = "StartBackupHandler.post(): "
       
        logging.debug(fn_name + "<Start>")
        logservice.flush()

        try:
            # DEBUG
            if self.request.cookies.has_key('auth_count'):
                logging.debug(fn_name + "Cookie: auth_count = " + str(self.request.cookies['auth_count']))
            else:
                logging.debug(fn_name + "No auth_count cookie found")
            logservice.flush()            
                
            # client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)
            
            user, credentials = _GetCredentials()
            if user is None:
                logging.warning(fn_name + "user is None, redirecting to " +
                    settings.INVALID_CREDENTIALS_URL)
                logservice.flush()
                self.redirect(settings.INVALID_CREDENTIALS_URL + "?rc=NU")
                return
                
            if credentials is None or credentials.invalid:
                logging.warning(fn_name + "credentials is None or invalid, redirecting to " + 
                    settings.INVALID_CREDENTIALS_URL)
                logservice.flush()
                self.redirect(settings.INVALID_CREDENTIALS_URL + "?rc=XC")
                return
            
            logging.debug(fn_name + "Resetting auth_count cookie to zero")
            logservice.flush()
            _set_cookie(self.response, 'auth_count', '0', max_age=120)
            user_email = user.email()
            is_test_user = shared.isTestUser(user_email)
            if self.request.host in settings.LIMITED_ACCESS_SERVERS:
                logging.debug(fn_name + "Running on limited-access server")
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
            tasks_backup_job.job_type = 'export'
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
            
            # Add the request to the tasks queue, passing in the user's email so that the task can access the
            # databse record
            q = taskqueue.Queue(settings.PROCESS_TASKS_REQUEST_QUEUE_NAME)
            t = taskqueue.Task(url=settings.WORKER_URL, params={settings.TASKS_QUEUE_KEY_NAME : user_email}, method='POST')
            logging.debug(fn_name + "Adding task to " + str(settings.PROCESS_TASKS_REQUEST_QUEUE_NAME) + 
                " queue, for " + str(user_email))
            logservice.flush()
            
            try:
                q.add(t)
            except exception, e:
                logging.exception(fn_name + "Exception adding task to taskqueue. Redirecting to " + str(settings.PROGRESS_URL))
                logservice.flush()
                self.redirect(settings.PROGRESS_URL + "?msg=Exception%20adding%20task%20to%20taskqueue")
                return

            logging.debug(fn_name + "Redirecting to " + settings.PROGRESS_URL)
            logservice.flush()
            self.redirect(settings.PROGRESS_URL)
            # logging.debug(fn_name + "Calling garbage collection")
            # gc.collect()
            logging.debug(fn_name + "<End>")
            logservice.flush()
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            self.response.out.write("""Sorry, something went terribly wrong.<br />%s<br />Please report this error to <a href="http://code.google.com/p/tasks-backup/issues/list">code.google.com/p/tasks-backup/issues/list</a>""" % str(e))
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
            # DEBUG
            if self.request.cookies.has_key('auth_count'):
                logging.debug(fn_name + "Cookie: auth_count = " + str(self.request.cookies['auth_count']))
            else:
                logging.debug(fn_name + "No auth_count cookie found")
            logservice.flush()            
                
            client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)
          
              
            user, credentials = _GetCredentials()
            if user is None:
                logging.warning(fn_name + "user is None, redirecting to " +
                    settings.INVALID_CREDENTIALS_URL)
                logservice.flush()
                self.redirect(settings.INVALID_CREDENTIALS_URL + "?rc=NU")
                return
                
            if credentials is None or credentials.invalid:
                logging.warning(fn_name + "credentials is None or invalid, redirecting to " + 
                    settings.INVALID_CREDENTIALS_URL)
                logservice.flush()
                self.redirect(settings.INVALID_CREDENTIALS_URL + "?rc=XC")
                return
            
            logging.debug(fn_name + "Resetting auth_count cookie to zero")
            logservice.flush()
            _set_cookie(self.response, 'auth_count', '0', max_age=120)    
            user_email = user.email()
            if self.request.host in settings.LIMITED_ACCESS_SERVERS:
                logging.debug(fn_name + "Running on limited-access server")
                if not shared.isTestUser(user_email):
                    logging.info(fn_name + "Rejecting non-test user on limited access server")
                    self.response.out.write("<h2>This is a test server. Access is limited to test users.</h2>")
                    logging.debug(fn_name + "<End> (restricted access)" )
                    logservice.flush()
                    return
            
            
            # Retrieve the DB record for this user
            tasks_backup_job = model.ProcessTasksJob.get_by_key_name(user_email)
                
            if tasks_backup_job is None:
                logging.error(fn_name + "No DB record for " + user_email)
                status = 'no-record'
                progress = 0
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
                
                if status != 'completed' and status != 'import_completed' and status != 'error':
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
            
            if status == 'completed':
                logging.info(fn_name + "Retrieved " + str(progress) + " tasks for " + str(user_email))
            elif status == 'import_completed':
                logging.info(fn_name + "Imported " + str(progress) + " tasks for " + str(user_email))
            else:
                logging.debug(fn_name + "Status = " + str(status) + ", progress = " + str(progress) + 
                    " for " + str(user_email) + ", started at " + str(job_start_timestamp) + " UTC")
            
            if error_message:
                logging.error(fn_name + "Error message: " + str(error_message))
            
            path = os.path.join(os.path.dirname(__file__), _path_to_templates, "progress.html")
            
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
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            self.response.out.write("""Sorry, something went terribly wrong.<br />%s<br />Please report this error to <a href="http://code.google.com/p/tasks-backup/issues/list">code.google.com/p/tasks-backup/issues/list</a>""" % str(e))
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()
        
          
class ReturnResultsHandler(webapp.RequestHandler):
    """Handler to return results to user in the requested format """
    
    def get(self):
        """ If user attempts to go direct to /results, we redirect to /progress so user can choose format """
        fn_name = "ReturnResultsHandler.get(): "
        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        try:
            logging.info(fn_name + "Expected POST for " + str(settings.RESULTS_URL) + 
                            ", so redirecting to " + str(settings.PROGRESS_URL))
            logservice.flush()
            # Display the progress page to allow user to choose format for results
            self.redirect(settings.PROGRESS_URL)
            # logging.debug(fn_name + "Calling garbage collection")
            # gc.collect()
            logging.debug(fn_name + "<End>")
            logservice.flush()
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            self.response.out.write("""Sorry, something went terribly wrong.<br />%s<br />Please report this error to <a href="http://code.google.com/p/tasks-backup/issues/list">code.google.com/p/tasks-backup/issues/list</a>""" % str(e))
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()
        
    def post(self):
        """ Return results to the user, in format chosen by user """
        fn_name = "ReturnResultsHandler.post(): "
        
        logging.debug(fn_name + "<Start>")
        logservice.flush()

        try:
            # DEBUG
            if self.request.cookies.has_key('auth_count'):
                logging.debug(fn_name + "Cookie: auth_count = " + str(self.request.cookies['auth_count']))
            else:
                logging.debug(fn_name + "No auth_count cookie found")
            logservice.flush()            
            
            client_id, client_secret, user_agent, app_title, product_name, host_msg = shared.GetSettings(self.request.host)
            
            user, credentials = _GetCredentials()
            if user is None:
                logging.warning(fn_name + "user is None, redirecting to " +
                    settings.INVALID_CREDENTIALS_URL)
                logservice.flush()
                self.redirect(settings.INVALID_CREDENTIALS_URL + "?rc=NU")
                return
                
            if credentials is None or credentials.invalid:
                logging.warning(fn_name + "credentials is None or invalid, redirecting to " + 
                    settings.INVALID_CREDENTIALS_URL)
                logservice.flush()
                self.redirect(settings.INVALID_CREDENTIALS_URL + "?rc=XC")
                return
            
            logging.debug(fn_name + "Resetting auth_count cookie to zero")
            logservice.flush()
            _set_cookie(self.response, 'auth_count', '0', max_age=120)
            user_email = user.email()
            is_test_user = shared.isTestUser(user_email)
            if self.request.host in settings.LIMITED_ACCESS_SERVERS:
                logging.debug(fn_name + "Running on limited-access server")
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
                job_start_timestamp = None
            else:            
                include_completed = tasks_backup_job.include_completed
                include_deleted = tasks_backup_job.include_deleted
                include_hidden = tasks_backup_job.include_hidden
                total_progress = tasks_backup_job.total_progress
                
            # Retrieve the data DB record for this user
            logging.debug(fn_name + "Retrieving details for " + str(user_email))
            
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
                self.response.set_status(412, "No data for this user. Please retry backup request.")
                return
            
            logging.debug(fn_name + "Reassembling tasks data from " + str(num_records) + " blobs")
            rebuilt_pkl = ""
            for tasklists_record in tasklists_records:
                #logging.debug("Reassembling blob number " + str(tasklists_record.idx))
                rebuilt_pkl = rebuilt_pkl + tasklists_record.pickled_tasks_data
                
            logging.debug(fn_name + "Reassembled " + str(len(rebuilt_pkl)) + " bytes")
            
            tasklists = pickle.loads(rebuilt_pkl)
            rebuilt_pkl = None # Not needed, so release it
            


            """
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
            display_completed_tasks = (self.request.get('dim_completed_tasks') == 'True')
            dim_completed_tasks = (self.request.get('dim_completed_tasks') == 'True')
            display_completed_date_field = (self.request.get('display_completed_date_field') == 'True')
            display_due_date_field = (self.request.get('display_due_date_field') == 'True')
            display_updated_date_field = (self.request.get('display_updated_date_field') == 'True')
            display_invalid_tasks = (self.request.get('display_invalid_tasks') == 'True')
            due_selection = self.request.get('due_selection')
            
            logging.debug(fn_name + "Selected format = " + str(export_format))

            # Filename format is "tasks_FORMAT_EMAILADDR_YYYY-MM-DD.EXT"
            # CAUTION: Do not include characters that may not be valid on some filesystems (e.g., colon is not valid on Windows)
            output_filename_base = "tasks_%s_%s_%s" % (export_format, user_email, datetime.datetime.now().strftime("%Y-%m-%d"))
     
            if due_selection in ['due_now', 'overdue']:
                # If user selected to display due or iverdue tasks, use this value to determine which tasks to display.
                # Using value from user's browser, since that will be in user's current timezone. Server doesn't know user's current timesone.
                logging.debug(fn_name + "User chose to only display tasks due, where due_year = " + str(self.request.get('due_year')) +
                                ", due_month = " + str(self.request.get('due_month')) +
                                ", due_day = " + str(self.request.get('due_day')))
                try:
                    due_date_limit = datetime.date(int(self.request.get('due_year')),
                                                int(self.request.get('due_month')), 
                                                int(self.request.get('due_day'))) 
                except Exception, e:
                    due_date_limit = datetime.date(datetime.MINYEAR,1,1)
                    logging.exception(fn_name + "Error intepretting date from browser. Using " + str(due_date_limit))
            else:
                due_date_limit = None
            logging.debug(fn_name + "due_selection = " + str(due_selection) + "due_date_limit = " + str(due_date_limit) )
                
            # Calculate and add 'depth' property
            for tasklist in tasklists:
                tasks = tasklist[u'tasks']
                
                num_tasks = len(tasks)
                if num_tasks > 0: # Non-empty tasklist
                    task_idx = 0
                    possible_parent_ids = []
                    possible_parent_is_active = []
                    
                    while task_idx < num_tasks:
                        task = tasks[task_idx]
                        # By default, assume parent is valid
                        task[u'parent_is_active'] = True

                        if task.has_key(u'parent'):
                            if task[u'parent'] in possible_parent_ids:
                                idx = possible_parent_ids.index(task[u'parent'])
                                try:
                                    task[u'parent_is_active'] = possible_parent_is_active[idx]
                                except Exception, e:
                                    logging.exception("idx = " + str(idx) + ", id = " + task[u'id'] + ", parent = " + task[u'parent'] + ", [" + task[u'title'] + "]")
                                    logging(possible_parent_ids)
                                    logging(possible_parent_is_active)
                                depth = idx + 1
                                task[u'depth'] = depth
                                
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
                                    task[u'depth'] = -1
                                else:
                                    # Non-deleted/hidden task with invalid parent.
                                    # This "orphan" non-hidden/deleted task has an unknown depth, since it's parent no longer exists. 
                                    # The parent task may have been deleted or moved.
                                    # One way this can happen:
                                    #       Start with A/B/C/D
                                    #       Delete D
                                    #       Delete C
                                    #       Restore D from Trash
                                    # This task is NOT displayed in any view by Google!
                                    if display_invalid_tasks:
                                        task[u'depth'] = -99
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
                            task[u'depth'] = 0
                        
                        task_idx = task_idx + 1   

                    # Add extra properties for HTML view;
                    #    Add 'indent' property for HTML pages so that tasks can be correctly indented
                    #    Determine if task should be displayed, based on user selections
                    if export_format == 'html_raw':
                        #logging.debug(fn_name + "Setting metadata for " + export_format + " format")
                        tasklist_has_tasks_to_display = False
                        for task in tasks:
                            display = True # Display by default
                            
                            # TODO: Determine if task should be displayed
                            if not display_completed_tasks and task[u'status'] == 'completed':
                                # User chose not to display completed tasks
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
                                    except Exception, e:
                                        logging.exception(fn_name + "Exception determining if task is due")
                                        logging.debug(fn_name + "Task ==>")
                                        logging.debug(task)
                            
                            task['display'] = display
                                
                            try:
                                depth = task[u'depth']
                            except KeyError, e:
                                logging.exception(fn_name + "Missing depth for " + task[u'id'] + ", " + task[u'title'])
                                task[u'depth'] = -2
                                depth = 0
                            if depth < 0:
                                depth = 0
                            # Set number of pixels to indent task by, as a string,
                            # to use in style="padding-left:nnn" in HTML pages
                            task[u'indent'] = str(depth * settings.TASK_INDENT).strip()
                                
                        if tasklist_has_tasks_to_display:
                            tasklist[u'tasklist_has_tasks_to_display'] = True
                    
            template_values = {'app_title' : app_title,
                               'host_msg' : host_msg,
                               'home_page_url' : settings.HOME_PAGE_URL,
                               'product_name' : product_name,
                               'tasklists': tasklists,
                               'total_progress' : total_progress,
                               'dim_completed_tasks' : dim_completed_tasks,
                               'due_selection' : due_selection,
                               'due_date_limit' : str(due_date_limit),
                               'display_invalid_tasks' : display_invalid_tasks,
                               'include_completed' : include_completed,
                               'include_deleted' : include_deleted,
                               'include_hidden' : include_hidden,
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
            elif export_format in ['outlook', 'raw', 'raw1', 'import_export']:
                self.WriteCsvUsingTemplate(template_values, export_format, output_filename_base)
            elif export_format == 'html_raw':
                self.WriteHtmlRaw(template_values)
            elif export_format == 'RTM':
                self.SendEmailUsingTemplate(template_values, export_format, user_email, output_filename_base)
            elif export_format == 'py':
                self.WriteTextUsingTemplate(template_values, export_format, output_filename_base, 'py')
            else:
                logging.warning(fn_name + "Unsupported export format: %s" % export_format)
                # TODO: Handle invalid export_format nicely - display message to user & go back to main page
                self.response.out.write("<br /><h2>Unsupported export format: %s</h2>" % export_format)
            tasklists = None
            logging.debug(fn_name + "Calling garbage collection")
            gc.collect()
            logging.debug(fn_name + "<End>")
            logservice.flush()
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            self.response.out.write("""Sorry, something went terribly wrong.<br />%s<br />Please report this error to <a href="http://code.google.com/p/tasks-backup/issues/list">code.google.com/p/tasks-backup/issues/list</a>""" % str(e))
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()

        
    def SendEmailUsingTemplate(self, template_values, export_format, user_email, output_filename_base):
        """ Send an email, formatted according to the specified .txt template file
            Currently supports export_format = 'RTM' (Remember The Milk)
        """
        # Potential TODO items (if email quota is sufficient)
        #   TODO: Allow other formats
        #   TODO: Allow attachments (e.g. Outlook CSV) ???
        #   TODO: Improve subject line
        fn_name = "SendEmailUsingTemplate(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        # if shared.isTestUser(user_email):
          # logging.debug(fn_name + "Creating email body using template")
        # Use a template to convert all the tasks to the desired format 
        template_filename = "tasks_template_%s.txt" % export_format
        
        path = os.path.join(os.path.dirname(__file__), _path_to_templates, template_filename)
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
            self.response.out.write("""Sorry, unable to send email due to quota limitations of my AppSpot account.
                                       <br />
                                       It may be that your email is too large, or that to many emails have been sent by others in the past 24 hours.
                                    """)
            logging.debug(fn_name + "<End> (due to exception)")
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

        path = os.path.join(os.path.dirname(__file__), _path_to_templates, template_filename)
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
            Currently supports export_format = 'outlook', 'raw', 'raw1' and 'import_export'
        """
        fn_name = "WriteCsvUsingTemplate(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        template_filename = "tasks_template_%s.csv" % export_format
        output_filename = output_filename_base + ".csv"
        self.response.headers["Content-Type"] = "text/csv"
        self.response.headers.add_header(
            "Content-Disposition", "attachment; filename=%s" % output_filename)

        
        path = os.path.join(os.path.dirname(__file__), _path_to_templates, template_filename)
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
            Currently supports export_format = 'py' 
        """
        fn_name = "WriteTextUsingTemplate(): "

        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        template_filename = "tasks_template_%s.%s" % (export_format, file_extension)
        output_filename = output_filename_base + "." + file_extension
        self.response.headers["Content-Type"] = "text/plain"
        self.response.headers.add_header(
            "Content-Disposition", "attachment;filename=%s" % output_filename)

        
        path = os.path.join(os.path.dirname(__file__), _path_to_templates, template_filename)
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


    def WriteHtmlRaw(self, template_values):
        """ Manually build an HTML representation of the user's tasks.
        
            This method creates the page manually, which uses significantly less memory than using Django templates.
            It is also faster, but does not support multi-line notes. Notes are displayed on a single line.
        """
        
        fn_name = "WriteHtmlRaw() "
        
        user_email = template_values.get('user_email')
        logout_url = template_values.get('logout_url')
        tasklists = template_values.get('tasklists')
        total_progress = template_values.get('total_progress')
        include_completed = template_values.get('include_completed')
        include_hidden = template_values.get('include_hidden')
        include_deleted = template_values.get('include_deleted')
        display_invalid_tasks = template_values.get('display_invalid_tasks')
        job_start_timestamp = template_values.get('job_start_timestamp')
        dim_completed_tasks = template_values.get('dim_completed_tasks')
        due_selection = template_values.get('due_selection')
        due_date_limit = template_values.get('due_date_limit')
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
                <link rel="stylesheet" type="text/css" href="static/tasks_backup.css"></link>
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
            self.response.out.write(""" UTC</h3>""")
            self.response.out.write("""<div class="break">Backup completed. Retrieved """)
            self.response.out.write(total_progress)
            self.response.out.write(""" tasks from """)
            self.response.out.write(num_tasklists)
            self.response.out.write(""" task lists.""")
            
            if due_selection in ['any_due', 'due_now', 'overdue']:
                self.response.out.write("""<br />
                    <span class="comment">Displaying """)
                if due_selection == 'any_due':
                    self.response.out.write("""tasks with any due date""")
                elif due_selection == 'due_now':
                    self.response.out.write("""current tasks (due on or before """ + str(due_date_limit) + """)""")
                elif due_selection == 'overdue':
                    self.response.out.write("""overdue tasks (due before """ + str(due_date_limit) + """)""")
                self.response.out.write("""</span>""")
            if include_completed:
                self.response.out.write("""<br />
                    <span class="comment">Displaying completed tasks</span>""")
            if include_hidden:
                self.response.out.write("""<br />
                    <span class="comment">Displaying hidden tasks</span>""")
            if include_deleted:
                self.response.out.write("""<br />
                    <span class="comment">Displaying deleted tasks</span>""")
            if display_invalid_tasks:
                self.response.out.write("""<br />
                    <span class="comment">Displaying invalid/corrupted tasks</span>""")
            self.response.out.write("""</div>""")
                    
            for tasklist in tasklists:
                if not tasklist.get('tasklist_has_tasks_to_display', False):
                    # Skip tasklists that don't have any due tasks
                    continue
                    
                num_tasks = len(tasklist)
                if num_tasks > 0:
                
                    tasklist_title = tasklist.get(u'title')
                    if len(tasklist_title.strip()) == 0:
                        tasklist_title = "<Unnamed Tasklist>"
                    tasklist_title = shared.EscapeHtml(tasklist_title)

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
                        if not task.get(u'display', True):
                            # Skip tasks that don't match user's selection
                            continue
                    
                        task_title = task.get(u'title', "<No Task Title>")
                        if len(task_title.strip()) == 0:
                            task_title = "<Unnamed Task>"
                        task_title = shared.EscapeHtml(task_title)
                        
                        task_notes = shared.EscapeHtml(task.get(u'notes', None))
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
                        # End of task details div
                        # End of task div
                        self.response.out.write("""</div></div>""")
                        
                    # End of tasks div
                    self.response.out.write("""</div>""")
                                           
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
               
        
class OAuthHandler(webapp.RequestHandler):
    """Handler for /oauth2callback."""

    # TODO: Simplify - Compare with orig in GTP
    def get(self):
        """Handles GET requests for /oauth2callback."""
        fn_name = "OAuthHandler.get() "
        
        try:
            if not self.request.get("code"):
                logging.debug(fn_name + "No 'code', so redirecting to /")
                logservice.flush()
                self.redirect("/")
                return
            user = users.get_current_user()
            logging.debug(fn_name + "Retrieving flow for " + str(user.user_id()))
            flow = pickle.loads(memcache.get(user.user_id()))
            if flow:
                logging.debug(fn_name + "Got flow. Retrieving credentials")
                error = False
                retry_count = 3
                while retry_count > 0:
                    try:
                        credentials = flow.step2_exchange(self.request.params)
                        break
                    except client.FlowExchangeError, e:
                        logging.warning(fn_name + "FlowExchangeError " + str(e))
                        credentials = None
                        error = True
                    except Exception, e:
                        if retry_count > 0:
                            logging.exception(fn_name + "Error retrieving credentials. " + 
                                    str(retry_count) + " retries remaining")
                            logservice.flush()
                        else:
                            logging.exception(fn_name + "Unable to retrieve credentials after 3 retries. Redirecting to " + settings.INVALID_CREDENTIALS_URL)
                            logservice.flush()
                            self.redirect(settings.INVALID_CREDENTIALS_URL + "?rc=EX&err=" + str(type(e)))
                            return
                    retry_count = retry_count - 1
                    
                appengine.StorageByKeyName(
                    model.Credentials, user.user_id(), "credentials").put(credentials)
                if error:
                    logging.warning(fn_name + "FlowExchangeError, redirecting to '/?msg=ACCOUNT_ERROR'")
                    logservice.flush()
                    self.redirect("/?msg=ACCOUNT_ERROR")
                else:
                    # logging.debug(fn_name + "Retrieved credentials ==>")
                    # shared.DumpObj(credentials)
                    # logservice.flush()
                    
                    if not credentials:
                        logging.debug(fn_name + "No credentials. Redirecting to " + settings.INVALID_CREDENTIALS_URL)
                        # logging.debug(fn_name + "user ==>")
                        # shared.DumpObj(user)
                        logservice.flush()
                        self.redirect(settings.INVALID_CREDENTIALS_URL + "?rc=NC")
                    elif credentials.invalid:
                        logging.warning(fn_name + "Invalid credentials. Redirecting to " + settings.INVALID_CREDENTIALS_URL)
                        # logging.debug(fn_name + "user ==>")
                        # shared.DumpObj(user)
                        # logging.debug(fn_name + "credentials ==>")
                        # shared.DumpObj(credentials)
                        logservice.flush()
                        self.redirect(settings.INVALID_CREDENTIALS_URL + "?rc=IC")
                    else:
                        logging.debug(fn_name + "Credentials valid. Redirecting to " + str(self.request.get("state")))
                        logservice.flush()
                        # logging.debug(fn_name + "Resetting auth_count cookie to zero")
                        # logservice.flush()
                        # _set_cookie(self.response, 'auth_count', '0', max_age=120)
                        
                        self.redirect(self.request.get("state"))
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            self.response.out.write("""Sorry, something went terribly wrong.<br />%s<br />Please report this error to <a href="http://code.google.com/p/tasks-backup/issues/list">code.google.com/p/tasks-backup/issues/list</a>""" % str(e))
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()

        
def real_main():
    logging.debug("main(): Starting tasks-backup (app version %s)" %appversion.version)
    template.register_template_library("common.customdjango")

    application = webapp.WSGIApplication(
        [
            (settings.HOME_PAGE_URL,            MainHandler),
            (settings.RESULTS_URL,              ReturnResultsHandler),
            (settings.START_BACKUP_URL,         StartBackupHandler),
            (settings.PROGRESS_URL,             ShowProgressHandler),
            (settings.INVALID_CREDENTIALS_URL,  InvalidCredentialsHandler),
            (settings.GET_NEW_BLOBSTORE_URL,    GetNewBlobstoreUrlHandler),
            (settings.BLOBSTORE_UPLOAD_URL,     BlobstoreUploadHandler),
            ("/completed",                      CompletedHandler),
            ("/auth",                           AuthRedirectHandler),
            ("/oauth2callback",                 OAuthHandler),
        ], debug=False)
    util.run_wsgi_app(application)
    logging.debug("main(): <End>")

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
    
main = real_main

if __name__ == "__main__":
    main()

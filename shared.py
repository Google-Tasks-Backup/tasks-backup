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
#
# Original Google Tasks Porter, modified by Julie Smith 2012

# This module contains code whis is common between classes, or between tasks-backup.py and worker.py
# Can't use the name common, because there is already a module named common

from apiclient.oauth2client import appengine
from google.appengine.api import users
from google.appengine.api import logservice # To flush logs
from google.appengine.ext import db
from google.appengine.api import memcache
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template

from apiclient.oauth2client import client
from apiclient import discovery

# Import from error so that we can process HttpError
from apiclient import errors as apiclient_errors



import httplib2
import Cookie
import cgi
import sys
import os
import traceback
import logging
from google.appengine.api import logservice # To flush logs
import pickle
import model

# Project-specific settings, used by get_settings
import settings
import constants
import appversion # appversion.version is set before the upload process to keep the version number consistent


logservice.AUTOFLUSH_EVERY_SECONDS = 5
logservice.AUTOFLUSH_EVERY_BYTES = None
logservice.AUTOFLUSH_EVERY_LINES = 5
logservice.AUTOFLUSH_ENABLED = True

class DailyLimitExceededError(Exception):
    """ Thrown by get_credentials() when HttpError indicates that daily limit has been exceeded """
    
    msg = "Daily limit exceeded. Please try again after midnight Pacific Standard Time."
    
    def __init__(self, msg = None):
        if msg:
            self.msg = msg
            
    def __repr__(self):
        return msg;
    

def set_cookie(res, key, value='', max_age=None,
                   path='/', domain=None, secure=None, httponly=False,
                   version=None, comment=None):
    """
    Set (add) a cookie for the response
    """
    
    fn_name = "set_cookie(): "
    
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
    logging.debug(fn_name + "Writing cookie: '" + str(key) + "' = '" + str(value) + "', max age = '" + str(max_age) + "'")
    logservice.flush()
        
        
def delete_cookie(res, key):
    logging.debug("Deleting cookie: " + str(key))
    set_cookie(res, key, '', -1)
    
    
def __store_auth_retry_count(self, count):
    set_cookie(self.response, 'auth_retry_count', str(count), max_age=settings.AUTH_RETRY_COUNT_COOKIE_EXPIRATION_TIME)
    
    
def __reset_auth_retry_count(self):
    set_cookie(self.response, 'auth_retry_count', '0', max_age=settings.AUTH_RETRY_COUNT_COOKIE_EXPIRATION_TIME)
    
    
def redirect_for_auth(self, user, redirect_url=None):
    """Redirects the webapp response to authenticate the user with OAuth2.
    
        Args:
            redirect_url        [OPTIONAL] The URL to return to once authorised. 
                                Usually unused (left as None), so that the URL of the calling page is used
    
        Uses the 'state' parameter to store redirect_url. 
        The handler for /oauth2callback can therefore redirect the user back to the page they
        were on when get_credentials() failed (or to the specified redirect_url).
    """

    fn_name = "redirect_for_auth(): "
    
    try:
        client_id, client_secret, user_agent, app_title, product_name, host_msg = get_settings(self.request.host)
        
        
        # Check how many times this has been called (without credentials having been successfully retrieved)
        if self.request.cookies.has_key('auth_retry_count'):
            auth_retry_count = int(self.request.cookies['auth_retry_count'])
            logging.debug(fn_name + "auth_retry_count = " + str(auth_retry_count))
            if auth_retry_count > settings.MAX_NUM_AUTH_RETRIES:
                # Exceeded maximum number of retries, so don't try again.
                # Redirect user to invalid credentials page
                logging.warning(fn_name + "Not re-authorising, because there have already been " + str(auth_retry_count) + 
                    " attempts. Redirecting to " + settings.INVALID_CREDENTIALS_URL)
                self.redirect(settings.INVALID_CREDENTIALS_URL + "?rc=NC&nr=" + str(auth_retry_count))
                return
        else:
            logging.debug(fn_name + "No auth_retry_count cookie found. Probably means last authorisation was more than " +
                str(settings.AUTH_RETRY_COUNT_COOKIE_EXPIRATION_TIME) + " seconds ago")
            auth_retry_count = 0
                
        if not redirect_url:
            # By default, return to the same page
            redirect_url = self.request.path_qs
            
        # According to https://developers.google.com/accounts/docs/OAuth_ref#RequestToken
        # xoauth_displayname is optional. 
        #     (optional) String identifying the application. 
        #     This string is displayed to end users on Google's authorization confirmation page. 
        #     For registered applications, the value of this parameter overrides the name set during registration and 
        #     also triggers a message to the user that the identity can't be verified. 
        #     For unregistered applications, this parameter enables them to specify an application name, 
        #     In the case of unregistered applications, if this parameter is not set, Google identifies the application 
        #     using the URL value of oauth_callback; if neither parameter is set, Google uses the string "anonymous".
        # It seems preferable to NOT supply xoauth_displayname, so that Google doesn't display "identity can't be verified" msg.
        flow = client.OAuth2WebServerFlow(
            client_id=client_id,
            client_secret=client_secret,
            scope="https://www.googleapis.com/auth/tasks",
            user_agent=user_agent,
            state=redirect_url)

        callback = self.request.relative_url("/oauth2callback")
        authorize_url = flow.step1_get_authorize_url(callback)
        memcache.set(user.user_id(), pickle.dumps(flow))
        
        # Keep track of how many times we've called the authorise URL
        if self.request.cookies.has_key('auth_retry_count'):
            auth_retry_count = int(self.request.cookies['auth_retry_count'])
        else:
            auth_retry_count = 0
        __store_auth_retry_count(self, auth_retry_count + 1)

        logging.debug(fn_name + "Redirecting to " + str(authorize_url))
        logservice.flush()
        self.redirect(authorize_url)
        
    except Exception, e:
        logging.exception(fn_name + "Caught top-level exception")
        self.response.out.write("""Oops! Something went terribly wrong.<br />%s<br />Please report this error to <a href="http://code.google.com/p/tasks-backup/issues/list">code.google.com/p/tasks-backup/issues/list</a>""" % get_exception_msg(e))
        logging.debug(fn_name + "<End> due to exception" )
        logservice.flush()

  
def get_credentials(self):
    """ Retrieve credentials for the user
            
        Returns:
            result              True if we have valid credentials for the user
            user                User object for current user
            credentials         Credentials object for current user. None if no credentials.
            fail_msg            If result==False, message suitabale for displaying to user
            fail_reason         If result==False, cause of the failure. Can be one of
                                    "User not logged on"
                                    "No credentials"
                                    "Invalid credentials"
                                    "Credential use error" (Unspecified error when attempting to use credentials)
                                    "Credential use HTTP error" (Returned an HTTP error when attempting to use credentials)
            
            
        If no credentials, or credentials are invalid, the calling method can call redirect_for_auth(self, user), 
        which sets the redirect URL back to the calling page. That is, user is redirected to calling page after authorising.
        
    """    
        
    fn_name = "get_credentials(): "
    
    user = None
    fail_msg = ''
    fail_reason = ''
    credentials = None
    result = False
    try:
        user = users.get_current_user()

        if user is None:
            # User is not logged in, so there can be no credentials.
            fail_msg = "User is not logged in"
            fail_reason = "User not logged on"
            logging.debug(fn_name + fail_msg)
            logservice.flush()
            return False, None, None, fail_msg, fail_reason
            
        credentials = appengine.StorageByKeyName(
            model.Credentials, user.user_id(), "credentials").get()
            
        result = False
        
        if credentials:
            if credentials.invalid:
                # We have credentials, but they are invalid
                fail_msg = "Invalid credentials for this user"
                fail_reason = "Invalid credentials"
                result = False
            else:
                #logging.debug(fn_name + "Calling tasklists service to confirm valid credentials")
                # so it turns out that the method that checks if the credentials are okay
                # doesn't give the correct answer unless you try to refresh it.  So we do that
                # here in order to make sure that the credentials are valid before being
                # passed to a worker.  Obviously if the user revokes the credentials after
                # this point we will continue to get an error, but we can't stop that.
                
                # Credentials are possibly valid, but need to be confirmed by refreshing
                # Try multiple times, just in case call to server fails due to external probs (e.g., timeout)
                # retry_count = settings.NUM_API_TRIES
                # while retry_count > 0:
                try:
                    http = httplib2.Http()
                    http = credentials.authorize(http)
                    service = discovery.build("tasks", "v1", http)
                    tasklists_svc = service.tasklists()
                    tasklists_list = tasklists_svc.list().execute()
                    # Successfully used credentials, everything is OK, so break out of while loop 
                    fail_msg = ''
                    fail_reason = ''
                    result = True
                    # break 
                    
                except apiclient_errors.HttpError, e:
                    logging.info(fn_name + "HttpError using credentials: " + get_exception_msg(e))
                    if e._get_reason().lower() == "daily limit exceeded":
                        fail_reason = "Daily limit exceeded"
                        fail_msg = "HttpError: Daily limit exceeded using credentials."
                    else:
                        fail_reason = "Credential use HTTP error"
                        fail_msg = "Error accessing tasks service: " + e._get_reason()
                    result = False
                    credentials = None
                    result = False
                    
                except Exception, e:
                    logging.info(fn_name + "Exception using credentials: " + get_exception_msg(e))
                    fail_reason = "Credential use error"
                    fail_msg = "System error: " + get_exception_msg(e)
                    credentials = None
                    result = False
                        
                    # retry_count = retry_count - 1
                    # if retry_count > 0:
                        # logging.debug(fn_name + "Error checking that credentials are valid, " + 
                            # str(retry_count) + " retries remaining: " + get_exception_msg(e))
                    # else:
                        # logging.exception(fn_name + "Still errors checking that credentials are valid, even after " +
                            # str(settings.NUM_API_TRIES) + " retries")
                        # credentials = None
                        # result = False
        else:
            # No credentials
            fail_msg = "No credentials"
            fail_reason = "Unable to retrieve credentials for user"
            logging.debug(fn_name + fail_msg)
            result = False
       
        if result:
            # TODO: Successfuly retrieved credentials, so reset auth_retry_count to 0
            __reset_auth_retry_count(self)
        else:
            logging.debug(fn_name + fail_msg)
            logservice.flush()
                
    except Exception, e:
        logging.exception(fn_name + "Caught top-level exception")
        logging.debug(fn_name + "<End> due to exception" )
        raise e
        
    if fail_reason == "Daily limit exceeded":
        # Will be caught in calling method's outer try-except
        raise DailyLimitExceededError()
        
    return result, user, credentials, fail_msg, fail_reason

  
def serve_message_page(self, msg1, msg2 = None, msg3 = None, 
        show_back_button=False, 
        back_button_text="Back to previous page",
        show_custom_button=False, custom_button_text='Try again', custom_button_url=settings.MAIN_PAGE_URL,
        show_heading_messages=True):
    """ Serve message.html page to user with message, with an optional button (Back, or custom URL)
    
        msg1, msg2, msg3        Text to be displayed.msg2 and msg3 are option. Each msg is displayed in a separate div
        show_back_button        If True, a [Back] button is displayed, to return to previous page
        show_custom_button      If True, display button to jump to any URL. title set by custom_button_text
        custom_button_text      Text label for custom button
        custom_button_url       URL to go to when custom button is pressed
        show_heading_messages   If True, display app_title and (optional) host_msg
    """
    fn_name = "serve_message_page: "

    logging.debug(fn_name + "<Start>")
    logservice.flush()
    
    try:
        client_id, client_secret, user_agent, app_title, product_name, host_msg = get_settings(self.request.host)

        if msg1:
            logging.debug(fn_name + "Msg1: " + msg1)
        if msg2:
            logging.debug(fn_name + "Msg2: " + msg2)
        if msg3:
            logging.debug(fn_name + "Msg3: " + msg3)
            
        path = os.path.join(os.path.dirname(__file__), constants.PATH_TO_TEMPLATES, "message.html")
          
        template_values = {'app_title' : app_title,
                           'host_msg' : host_msg,
                           'msg1': msg1,
                           'msg2': msg2,
                           'msg3': msg3,
                           'show_heading_messages' : show_heading_messages,
                           'show_back_button' : show_back_button,
                           'back_button_text' : back_button_text,
                           'show_custom_button' : show_custom_button,
                           'custom_button_text' : custom_button_text,
                           'custom_button_url' : custom_button_url,
                           'product_name' : product_name,
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
        self.response.out.write("""Oops! Something went terribly wrong.<br />%s<br />Please report this error to <a href="http://code.google.com/p/tasks-backup/issues/list">code.google.com/p/tasks-backup/issues/list</a>""" % get_exception_msg(e))
        logging.debug(fn_name + "<End> due to exception" )
        logservice.flush()
    

def format_exception_info(maxTBlevel=5):
    cla, exc, trbk = sys.exc_info()
    excName = cla.__name__
    try:
        excArgs = exc.__dict__["args"]
    except KeyError:
        excArgs = "<no args>"
    excTb = traceback.format_tb(trbk, maxTBlevel)
    return (excName, excArgs, excTb)
         

def get_exception_name(maxTBlevel=5):
    cla, exc, trbk = sys.exc_info()
    excName = cla.__name__
    return str(excName)
         

def get_exception_msg(e, maxTBlevel=5):
    cla, exc, trbk = sys.exc_info()
    excName = cla.__name__
    return str(excName) + ": " + str(e)
         

def delete_blobstore(blob_info):
    fn_name = "delete_blobstore(): "
    logging.debug(fn_name + "<Start>")
    logservice.flush()
    
    if blob_info:
        # -------------------------------------
        #       Delete the Blobstore item
        # -------------------------------------
        try:
            blob_info.delete()
            logging.debug(fn_name + "Blobstore deleted")
            logservice.flush()
        except Exception, e:
            logging.exception(fn_name + "Exception deleting " + file_name + ", key = " + blob_key)
            logservice.flush()
    else:
        logging.warning(fn_name + "No blobstore to delete")
        logservice.flush()

    logging.debug(fn_name + "<End>")
    logservice.flush()
    

def get_settings(hostname):
    """ Returns a tuple with hostname-specific settings
    args
        hostname         -- Name of the host on which this particular app instance is running,
                        as returned by self.request.host
    returns
        client_id        -- The OAuth client ID for app instance running on this particular host
        client_secret    -- The OAuth client secret for app instance running on this particular host
        user_agent       -- The user agent string for app instance running on this particular host
        app_title        -- The page title string for app instance running on this particular host
        product_name     -- The name displayed on the "Authorised Access to your Google account" page
        host_msg         -- An optional message which is displayed on some web pages, 
                        for app instance running on this particular host
    """

    if hostname.lower().startswith("www."):
        # If user accessed the service using www.XXXXXX.appspot.com, strip the "www." so we can match settings
        hostname = hostname[4:]
        
    if settings.client_ids.has_key(hostname):
        client_id = settings.client_ids[hostname]
    else:
        client_id = None
        raise KeyError("No ID entry in settings module for host = %s\nPlease check the address" % hostname)
  
    if settings.client_secrets.has_key(hostname):
        client_secret = settings.client_secrets[hostname]
    else:
        client_secret = None
        raise KeyError("No secret entry in settings module for host = %s\nPlease check the address" % hostname)
  
    if hasattr(settings, 'user_agents') and settings.user_agents.has_key(hostname):
        user_agent = settings.user_agents[hostname]
    else:
        user_agent = settings.DEFAULT_USER_AGENT

    if hasattr(settings, 'app_titles') and settings.app_titles.has_key(hostname):
        app_title = settings.app_titles[hostname]
    else:
        app_title = settings.DEFAULT_APP_TITLE
        
    if hasattr(settings, 'product_names') and settings.product_names.has_key(client_id):
        product_name = settings.product_names[client_id]
    else:
        product_name = settings.DEFAULT_PRODUCT_NAME
  
    if hasattr(settings, 'host_msgs') and settings.host_msgs.has_key(hostname):
        host_msg = settings.host_msgs[hostname]
    else:
        host_msg = None
  
    return client_id, client_secret, user_agent, app_title, product_name, host_msg
  

def isTestUser(user_email):
    """ Returns True if user_email is one of the defined settings.TEST_ACCOUNTS 
  
        Used when testing to ensure that only test user's details and sensitive data are logged.
    """
    return (user_email.lower() in (email.lower() for email in settings.TEST_ACCOUNTS))
  

def dump_obj(obj):
    for attr in dir(obj):
        logging.debug("    obj.%s = %s" % (attr, getattr(obj, attr)))
    logservice.flush()

    
def escape_html(text):
    """Ensure that text is properly escaped as valid HTML"""
    if text is None:
        return None
    return cgi.escape(text).encode('ascii', 'xmlcharrefreplace').replace('\n','<br />')
    #return cgi.escape(text.decode('unicode_escape')).replace('\n', '<br />')
    #return "".join(html_escape_table.get(c,c) for c in text)

    
# TODO: Untested
# def runningOnDev():
    # """ Returns true when running on local dev server. """
    # return os.environ['SERVER_SOFTWARE'].startswith('Dev')

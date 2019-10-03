# -*- coding: utf-8 -*-
#
# Copyright 2012  Julie Smith.  All Rights Reserved.
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
# Portions of this code are from Dwight Guth's Google Tasks Porter

# This module contains code whis is common between classes, modules or related projects
# Can't use the name common, because there is already a module named common

# import Cookie
import cgi
import sys
import os
import traceback
import logging
import datetime
import base64
import unicodedata
from urlparse import urljoin


from google.appengine.api import logservice # To flush logs
from google.appengine.api import mail
from google.appengine.api import urlfetch
from google.appengine.api.app_identity import get_application_id
from google.appengine.ext.webapp import template

from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Cipher import AES
from Crypto.Util import Counter

# Project-specific imports
import settings # pylint: disable=relative-import
import constants # pylint: disable=relative-import
import appversion # appversion.version is set before the upload process to keep the version number consistent # pylint: disable=relative-import
import host_settings # pylint: disable=relative-import


# Fix for DeadlineExceeded, because "Pre-Call Hooks to UrlFetch Not Working"
#     Based on code from https://groups.google.com/forum/#!msg/google-appengine/OANTefJvn0A/uRKKHnCKr7QJ
real_fetch = urlfetch.fetch # pylint: disable=invalid-name
def fetch_with_deadline(url, *args, **argv):
    argv['deadline'] = settings.URL_FETCH_TIMEOUT
    return real_fetch(url, *args, **argv)
urlfetch.fetch = fetch_with_deadline


logservice.AUTOFLUSH_EVERY_SECONDS = 5
logservice.AUTOFLUSH_EVERY_BYTES = None
logservice.AUTOFLUSH_EVERY_LINES = 5
logservice.AUTOFLUSH_ENABLED = True



class DailyLimitExceededError(Exception):
    """ Thrown by get_credentials() when HttpError indicates that daily limit has been exceeded """
    
    msg = "Daily limit exceeded. Please try again after midnight Pacific Standard Time."
    
    def __init__(self, msg = None): # pylint: disable=super-init-not-called
        if msg:
            self.msg = msg



class GtbDecryptionError(Exception):
    """ Indicates that encrypted tasks could not be decrypted.
    
        msg indicates why
    """
    
    def __init__(self, msg): # pylint: disable=super-init-not-called
        self.msg = msg
        super(GtbDecryptionError, self).__init__(msg)

    

def set_cookie( # pylint: disable=too-many-arguments
    req, name, val, use_request_path=False, path='/', cookie_name_prefix=''):
    """ Sets a cookie on the client

    Args:
        req, RequestHandler: The 'self' value used in get() and post() methods
        name, string: The name of the cookie
        val, string: The value to be stored
        use_request_path, bool: If True, use the request path, else use 'path' value
        path, string: Specifies the cookie path (if 'use_request_path' is False)
        cookie_name_prefix, string: Prefix to cookie_name

    This method sets the appropriate values for Expires.
    If the Domain and Path are not set, the cookie should be returned for all pages
    on the same domain that set the cookie.

    """
    if not isinstance(val, str):
        val = str(val)


    if cookie_name_prefix and name:
        name = cookie_name_prefix + '__' + name

    if not isinstance(path, str):
        path = str(path)

    if use_request_path:
        path = req.request.path

    # Expires in 10 years
    expires_dt = datetime.datetime.utcnow() + datetime.timedelta(days=10 * 365)
    
    secure = True
    # if is_dev_server():
        # secure = False
        # # From https://cloud.google.com/appengine/docs/python/config/appref#handlers_element
        # #   "The development web server does not support HTTPS connections."
        # if req._debug_level >= constants.DEBUG_LEVEL_VERY_DETAILED:
            # logging.debug("Dev server, so not using secure cookie")
    if is_dev_server() and req.request.scheme == 'http':
        # Running locally without https
        secure = False

    req.response.set_cookie(name, val, expires=expires_dt, overwrite=True, secure=secure, path=path)
    
    
def format_exception_info(max_tb_level=5):
    cla, exc, trbk = sys.exc_info()
    exc_name = cla.__name__
    try:
        exc_args = exc.__dict__["args"]
    except KeyError:
        exc_args = "<no args>"
    exc_tb = traceback.format_tb(trbk, max_tb_level)
    return (exc_name, exc_args, exc_tb)
         

def get_exception_name():
    cla, _, _ = sys.exc_info()
    exc_name = cla.__name__
    return str(exc_name)
         

def get_exception_msg(ex = None):
    """ Return string containing exception type and message
    
        args:
            ex       [OPTIONAL] An exception type
            
        If ex is specified, and is of an Exception type, this method returns a 
        string in the format "Type: Msg" 
        
        If ex is not specified, or cannot be parsed, "Type: Msg" is
        returned for the most recent exception
    """
    
    line_num = u''
    msg = u''
    ex_msg = u"No exception occured"
        
    # Store current exception msg, in case building msg for ex causes an exception
    cla, exc, trbk = sys.exc_info()
    try:
        line_num = trbk.tb_lineno
    except: # pylint: disable=bare-except
        pass
    if cla:
        exc_name = cla.__name__
        if line_num:
            ex_msg = u"{}: {} at line {}".format(exc_name, exc.message, line_num)
        else:
            ex_msg = u"{}: {}".format(exc_name, exc.message)
    
    if ex:
        try:
            e_msg = unicode(ex)
            exc_name = ex.__class__.__name__
            
            msg = "{}: {}".format(exc_name, e_msg)
            
        except: # pylint: disable=bare-except
            # Unable to parse passed-in exception 'ex', so returning the most recent
            # exception when this method was called
            msg = u"Unable to process 'ex'. Most recent exception = " + ex_msg

    if msg:
        return msg
    return ex_msg

         
def is_test_user(user_email):
    """ Returns True if user_email is one of the defined settings.TEST_ACCOUNTS 
  
        Used when testing to ensure that only test user's details and sensitive data are logged.
    """
    return (user_email.lower() in (email.lower() for email in settings.TEST_ACCOUNTS)) # pylint: disable=superfluous-parens
  

def dump_obj(obj):
    for attr in dir(obj):
        logging.debug("    obj.%s = %s" % (attr, getattr(obj, attr)))
    logservice.flush()

    
def escape_html(text):
    """Ensure that text is properly escaped as valid HTML"""
    if text is None:
        return None
    # From http://docs.python.org/howto/unicode.html
    #   .encode('ascii', 'xmlcharrefreplace')
    #   'xmlcharrefreplace' uses XML's character references, e.g. &#40960;
    return cgi.escape(text).encode('ascii', 'xmlcharrefreplace').replace('\n','<br />')
    #return cgi.escape(text.decode('unicode_escape')).replace('\n', '<br />')
    #return "".join(html_escape_table.get(c,c) for c in text)

                
def serve_quota_exceeded_page(self):
    msg1 = "Daily limit exceeded"
    msg2 = "The daily quota is reset at midnight Pacific Standard Time (5:00pm Australian Eastern Standard Time, 07:00 UTC)."
    msg3 = "Please rerun " + host_settings.APP_TITLE + " any time after midnight PST to continue importing your file."
    serve_message_page(self, msg1, msg2, msg3)
    
    
def serve_message_page(self,  # pylint: disable=too-many-locals
        msg1, msg2 = None, msg3 = None, 
        show_back_button=False, 
        back_button_text="Back to previous page",
        show_custom_button=False, custom_button_text='Try again', 
        custom_button_url = settings.MAIN_PAGE_URL,
        show_heading_messages=True,
        template_file="message.html",
        extra_template_values=None):
    """ Serve message.html page to user with message, with an optional button (Back, or custom URL)
    
        self                    A webapp.RequestHandler or similar
        msg1, msg2, msg3        Text to be displayed.msg2 and msg3 are option. Each msg is displayed in a separate div
        show_back_button        If True, a [Back] button is displayed, to return to previous page
        show_custom_button      If True, display button to jump to any URL. title set by custom_button_text
        custom_button_text      Text label for custom button
        custom_button_url       URL to go to when custom button is pressed. Should be an absolute URL
        show_heading_messages   If True, display app_title and (optional) host_msg
        template_file           Specify an alternate HTML template file
        extra_template_values   A dictionary containing values that will be merged with the existing template values
                                    They may be additional parameters, or overwrite existing parameters.
                                    These new values will be available to the HTML template.
                                    
        All args except self and msg1 are optional.
    """
    fn_name = "serve_message_page: "

    logging.debug(fn_name + "<Start>")
    logservice.flush()
    
    try:
        if custom_button_url:
            # Relative URLs sometimes fail on Firefox, so convert the default relative URL to an absolute URL
            
            if is_dev_server():
                scheme = 'http://'
            else:
                scheme = 'https://'
            custom_button_url = urljoin(scheme + self.request.host, custom_button_url)
    
        if msg1:
            logging.debug(fn_name + "Msg1: " + msg1)
        if msg2:
            logging.debug(fn_name + "Msg2: " + msg2)
        if msg3:
            logging.debug(fn_name + "Msg3: " + msg3)
            
        path = os.path.join(os.path.dirname(__file__), constants.PATH_TO_TEMPLATES, template_file)
          
        template_values = {'app_title' : host_settings.APP_TITLE,
                           'host_msg' : host_settings.HOST_MSG,
                           'msg1': msg1,
                           'msg2': msg2,
                           'msg3': msg3,
                           'show_heading_messages' : show_heading_messages,
                           'show_back_button' : show_back_button,
                           'back_button_text' : back_button_text,
                           'show_custom_button' : show_custom_button,
                           'custom_button_text' : custom_button_text,
                           'custom_button_url' : custom_button_url,
                           'product_name' : host_settings.PRODUCT_NAME,
                           'url_discussion_group' : settings.url_discussion_group,
                           'email_discussion_group' : settings.email_discussion_group,
                           'SUPPORT_EMAIL_ADDRESS' : settings.SUPPORT_EMAIL_ADDRESS,
                           'url_issues_page' : settings.url_issues_page,
                           'url_source_code' : settings.url_source_code,
                           'app_version' : appversion.version,
                           'upload_timestamp' : appversion.upload_timestamp}
                           
        if extra_template_values:
            # Add/update template values
            logging.debug(fn_name + "DEBUG: Updating template values ==>")
            logging.debug(extra_template_values)
            logservice.flush()
            template_values.update(extra_template_values)
            
        self.response.out.write(template.render(path, template_values))
        logging.debug(fn_name + "<End>" )
        logservice.flush()
    except Exception as ex: # pylint: disable=broad-except
        logging.exception(fn_name + "Caught top-level exception")
        serve_outer_exception_message(self, ex)
        logging.debug(fn_name + "<End> due to exception" )
        logservice.flush()
    

def serve_outer_exception_message(self, ex):
    """ Display an Oops message when something goes very wrong. 
    
        This is called from the outer exception handler of major methods (such as get/post handlers)
    """
    fn_name = "serve_outer_exception_message: "
    
    # self.response.out.write("""Oops! Something went terribly wrong.<br />%s<br /><br />This system is in beta, and is being actively developed.<br />Please report any errors to <a href="http://%s">%s</a> so that they can be fixed. Thank you.""" % 
        # ( get_exception_msg(ex), settings.url_issues_page, settings.url_issues_page))
        
    
    # NOTE: We are writing raw HTML here, as we don't know what may have happened. 
    # The tasks_backup.css has not been loaded, so we don't have access to our standard CSS classes, etc.
    self.response.out.write("""
        Oops! Something went terribly wrong:<br />
        {exception_msg}<br />
        <br />
        Please report this error
        <ul>
            <li>via Github at <a href="http://{url_issues_page}">{url_issues_page}</a></li>
            <li>or via the discussion group at <a href="http://{url_discussion_group}">{url_discussion_group}</a></li> 
            <li>or via email to <a href="mailto:{email_discussion_group}">{email_discussion_group}</a></li>
        </ul>
        so that it can be fixed. Thank you.
            """.format(
                    exception_msg=get_exception_msg(ex),
                    url_issues_page=settings.url_issues_page,
                    url_discussion_group=settings.url_discussion_group,
                    email_discussion_group=settings.email_discussion_group))
        
    logging.error(fn_name + get_exception_msg(ex))
    logservice.flush()

    send_email_to_support("Served outer exception message", get_exception_msg(ex))

    
def reject_non_test_user(self):
    fn_name = "reject_non_test_user: "
    
    logging.debug(fn_name + "Rejecting non-test user on limited access server")
    logservice.flush()
    
    # self.response.out.write("<html><body><h2>This is a test server. Access is limited to test users.</h2>" +
                    # "<br /><br /><div>Please use the production server at <href='http://tasks-backup.appspot.com'>tasks-backup.appspot.com</a></body></html>")
                    # logging.debug(fn_name + "<End> (restricted access)" )
    serve_message_page(self, 
        "This is a test server. Access is limited to test users.",
        "Please click the button to go to the production server at tasks-backup.appspot.com",
        show_custom_button=True, 
        custom_button_text='Go to live server', 
        custom_button_url='http://tasks-backup.appspot.com',
        show_heading_messages=False)
                    
                    
def format_datetime_as_str(dt, format_str, date_only=False, prefix=''): # pylint: disable=invalid-name
    """ Attempts to convert datetime to a string.
    
        dt              datetime object
        format_str      format string to be used by strftime
        date_only       If true, and strftime fails on the datetime object, then return a simplified date-only string
                        If false, and strftime fails on the datetime object, then return a simplified date & time string
                        
        The worker parses the RFC 3339 datetime strings retrieved from the server and converts that to datetime object.
        The earliest year that can be parsed by datetime.strptime() (or formatted by datetime.strftime) is 1900.
        Any strings that cannot be parsed by datetime.strptime() will be stored as a '1900-01-01 00:00:00' datetime object.
        
        However, if the datetime string is '0000-01-01T00:00:00.000Z', the worker stores None instead.
        In that case, we return the original '0000-01-01T00:00:00.000Z' string.
        
    """
    
    fn_name = "format_datetime_as_str: "
    
    try:
        datetime_str = ''
        if dt is None:
            # The original datestamp was '0000-01-01T00:00:00.000Z' which is stored as None,
            # so return a human-friendly representation of zero-date (i.e., '0000-01-01 00:00:00' or '0000-01-01')
            if date_only:
                datetime_str = constants.ZERO_DATE_STRING
            else:
                datetime_str = constants.ZERO_DATETIME_STRING
        else:
            try:
                datetime_str = dt.strftime(format_str)
            except Exception: # pylint: disable=broad-except
                try:
                    # Can't be formatted, so try to convert to a meaningful string manually
                    # This ignores the passed-in format string, but should at least provide something useful
                    if date_only:
                        datetime_str = "%04d-%02d-%02d" % (dt.year,dt.month,dt.day)
                    else:
                        datetime_str = "%04d-%02d-%02d %02d:%02d:%02d" % (
                            dt.year,dt.month,dt.day,dt.hour,dt.minute, dt.second)
                except Exception: # pylint: disable=broad-except
                    # Can't be converted (this should never happen)
                    logging.warning(fn_name + "Unable to convert datetime object; returning empty string")
                    return ''
        return prefix + datetime_str
        
    except Exception: # pylint: disable=broad-except
        logging.exception(fn_name + "Error processing datetime object; returning empty string")
        return ''
        
    
def convert_RFC3339_string_to_datetime( # pylint: disable=invalid-name
    datetime_str, field_name, date_only=False):
    """ Attempt to convert the RFC 3339 datetime string to a valid datetime object.
    
        If the field value cannot be parsed, return a default '1900-01-01 00:00:00' value.
        If the string is '0001-01-01T00:00:00.000Z', return None.
        
            datetime_str            String to be converted
            field_name              The name of the field being parsed. Only used for logging
            date_only               If True, return a date object instead of datetime
        
        strptime() can only parse dates after Jan 1900, but sometimes the server returns
        dates outside the valid range. Invalid values will be converted to 1900-01-01
        so that they can be parsed by strptime() or formatted by strftime()
        
        Parse the yyyy-mm-ddThh:mm:ss.dddZ return a date or datetime object.
        There have been occassional strange values in the 'completed' property, such as 
        "-1701567-04-26T07:12:55.000Z"
            According to http://docs.python.org/library/datetime.html
              "The exact range of years for which strftime() works also varies across platforms. 
               Regardless of platform, years before 1900 cannot be used."
        so if any date/timestamp value is invalid, set the property to '1900-01-01 00:00:00'
        
        NOTE: Sometimes a task has a completion date of '0000-01-01T00:00:00.000Z', which cannot
        be converted to datetime, because the earliest allowable datetime year is 0001, so that is
        returned as None
        
        Raises an exception if datetime_str is empty, or cannot be handled at all. In this case, it 
        is recommended that the calling method delete the associated field in the task object.
        
    """
    
    fn_name = "convert_RFC3339_string_to_datetime: "
    
    try:
        if not datetime_str:
            # Nothing to parse, so raise an Exception, so that the calling method can deal with it
            raise ValueError("No datetime string - nothing to parse")

        if datetime_str == constants.ZERO_RFC3339_DATETIME_STRING:
            # Zero timestamp is represented by None. 
            # Methods seeing None for a datetime object should replace it with a string representing 
            # the zero date (e.g., '0000-01-01 00:00:00')
            return None
            
        d = None
        try:
            # Parse the RFC 3339 datetime string
            d = datetime.datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S.000Z")
            
            # Test the resultant datetime to ensure that it can be displayed by strftime()
            # This prevents exceptions later when other modules try to display a datetime
            # that is outside the valid range for strftime(), such as dates before 1900.
            try:
                _ = d.strftime('%H:%M:%S %a, %d %b %Y')
            except Exception as ex: # pylint: disable=broad-except
                d = datetime.datetime(1900,1,1,0,0,0)
                logging.warning(fn_name + "Unable to convert '" + field_name + "' string '" + str(datetime_str) + 
                    "' to a datetime that can be displayed by strftime, so using " + str(d) + 
                    ": " + get_exception_msg(ex))
                logservice.flush()
            
        except ValueError as ve:
            # Minimum datestamp that can be parsed by strptime or displayed by strftime is 1900-01-01
            d = datetime.datetime(1900,1,1,0,0,0)
            logging.warning(fn_name + "Invalid '" + field_name + "' timestamp (" + str(datetime_str) + 
                "), so using " + str(d) + 
                ": " + get_exception_msg(ve))
            logservice.flush()
            
        except Exception as ex: # pylint: disable=broad-except
            logging.exception(fn_name + "Unable to parse '" + field_name + "' value '" + str(datetime_str) + 
                "' as a datetime")
            logservice.flush()
            raise ex
                
    except Exception as ex: # pylint: disable=broad-except
        # Catch all, in case we can't even process or display datetime_str
        logging.exception(fn_name + "Unable to parse '" + field_name + "' value")
        try:
            logging.error(fn_name + "Invalid value was '" + str(datetime_str) + "'")
        except Exception: # pylint: disable=broad-except
            logging.error(fn_name + "Error parsing datetime string, and unable to log invalid value: " + 
                get_exception_msg(ex))
        logservice.flush()
        raise ex
        
    if d and date_only:
        return d.date()
    return d
        
        
def set_timestamp(task, field_name, date_only=False):
    """ Parse timestamp field value and replace with a datetime object. 
    
            task                    A task dictionary object, as returned from the Google server
            field_name              The name of the field to be set
            date_only               If True, store a date object instead of datetime
        
        Parses the specified field and stores a date or datetime object so that methods which access
        the task (including Django templates) can format the displayed date.
        
        If there is a major problem, such as the field no being able to be parsed at all, we delete
        the field from the task dictionary.
    """
    
    fn_name = "set_timestamp: "
    try:
        if field_name in task:
            # Field exists, so try to parse its value
            try:
                datetime_str = task[field_name]
                task[field_name] = convert_RFC3339_string_to_datetime(datetime_str, field_name, date_only)
            except Exception as ex: # pylint: disable=broad-except
                try:
                    logging.error(fn_name + "Unable to parse '" + field_name + 
                        "' datetime field value '" + str(datetime_str) + "', so deleting field: " +
                        get_exception_msg(ex))
                except Exception: # pylint: disable=broad-except
                    # In case logging the value causes an exception, log without value
                    logging.error(fn_name + "Unable to parse '" + field_name + 
                        "' datetime field value, and unable to log field value, so deleting field: " +
                        get_exception_msg(ex))
                        
                # Delete the field which has the un-parseable value
                try:
                    del task[field_name]
                except Exception as ex2: # pylint: disable=broad-except
                    logging.error(fn_name + "Unable to delete '" + field_name + "': " + get_exception_msg(ex2))
                logservice.flush()
                
    except Exception: # pylint: disable=broad-except
        # This should never happen
        logging.exception(fn_name + "Error attempting to set '" + field_name + "' datetime field value, so deleting field")
        # Delete the field which caused the exception
        try:
            del task[field_name]
        except Exception as ex4: # pylint: disable=broad-except
            logging.error(fn_name + "Unable to delete '" + field_name + "': " + get_exception_msg(ex4))
        logservice.flush()
                  
                  
def convert_unicode_to_str(ustr):
    return unicodedata.normalize('NFKD', ustr).encode('ascii','ignore')                  
    

def ago_msg(hrs):
    """ Returns a string with "N hours ago" or "N days ago", depending how many hours """
    days = int(hrs / 24.0)
    minutes = int(hrs * 60)
    hrs = int(hrs)
    if minutes < 60:
        return "{} minutes ago".format(minutes)
    if hrs == 1:
        return "1 hour ago"
    if hrs < 24:
        return "{} hours ago".format(hrs)
    if days == 1:
        return "1 day ago"
    return "{} days ago".format(days)


def since_msg(job_start_timestamp): # pylint: disable=too-many-branches,too-many-statements
    """ Returns a human-friendly string indicating how long ago job_start_timestamp was """
    
    msg = ""
    job_execution_time = datetime.datetime.now() - job_start_timestamp

    mins = int(job_execution_time.total_seconds() / 60)
    hrs = mins / 60.0
    days = hrs / 24.0

    if mins < 10:
        # Don't display the actual time if less than 10 minutes,
        # because the actual backup job may take several minutes
        msg = " just now"
    elif mins < 60:
        # Round to the nearest 5 minutes for the first hour
        mins = round(mins / 5.0) * 5 
        msg = " {:g} minutes ago".format(mins)
    elif hrs < 2:
        # Round to the nearest 1/4 hr for the first 2 hrs
        hrs = round(hrs * 4) / 4
        if hrs == 1:
            msg = " an hour ago"
        else:
            msg = " {:g} hours ago".format(hrs)
    elif hrs < 6:
        # Round to the nearest 1/2 hr for the first 6 hrs
        hrs = round(hrs * 2) / 2
        msg = " {:g} hours ago".format(hrs)
    elif hrs <= 24:
        # Return whole hours for the first 24 hours
        msg = " {} hours ago".format(int(hrs))
    elif days <= 14:
        days = round(days * 2) / 2
        if days == 1:
            msg = " 1 day ago"
        elif days < 2:
            # Return the nearest 1/2 day for the first 2 days
            msg = " {:g} days ago".format(days)
        else:
            # Return whole days for up to 14 days
            days = int(days)
            msg = " {} days ago".format(days)
    elif days < 7 * 8:
        # Return whole weeks for up 8 weeks
        weeks = int(round(days / 7.0))
        if weeks == 1:
            msg = " a week ago"
        else:
            msg = " {} weeks ago".format(weeks)
    elif days < 366:
        # More than 8 weeks, so return whole months    
        months = int(round(days / 31.0))
        msg = " {} months ago".format(months)
    else:
        years = days / 365.0
        if years < 3:
            years = round(years * 2) / 2 # Round to 1/2 year 
            if years == 1:
                msg = " a year ago"
            else:
                msg = " {:g} years ago".format(years)
        else:
            years = int(years)
            msg = " more than {} years ago".format(years)
       
    return msg
    
    
def send_email_to_support(subject, msg, job_created_timestamp=None):
    """ Send an email to support.
    
        If possible 'subject' will be modified to make it unique to the current job,
        by including 'job_created_timestamp' in the subject line.
    """
    
    fn_name = "send_email_to_support: "
    
    try:
        # Without a unique subject line, Gmail would put all GTB error reports in one conversation.
        # Ideally, 'subject' should be common to a job, so that all errors relating to a single job
        # will be grouped in a single conversation, so we try to include the job creation time
        # in the subject line.
        # If we don't have a job creation time, we use the current time to ensure a unique subject.
        if job_created_timestamp:
            subject = u"{} v{} ({}) - ERROR for job created at {} - {}".format(
                settings.SUPPORT_EMAIL_ABBR_APP_NAME,
                # host_settings.APP_TITLE,
                appversion.version,
                appversion.app_yaml_version,
                job_created_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                subject)
        else:
            subject = u"{} v{} ({}) - ERROR at {} - {}".format(
                settings.SUPPORT_EMAIL_ABBR_APP_NAME,
                # host_settings.APP_TITLE,
                appversion.version,
                appversion.app_yaml_version,
                datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                subject)
        msg = "Timestamp = {} UTC\n{}",format(
            datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            msg)
        if not settings.SUPPORT_EMAIL_ADDRESS:
            logging.info(fn_name + "No support email address, so email not sent:")
            logging.info(fn_name + "    Subject = {}".format(subject))
            logging.info(fn_name + "    Msg = {}".format(msg))
            return
            
        logging.info(fn_name + "Sending support email:")
        logging.info(fn_name + "    Subject = {}".format(subject))
        logging.info(fn_name + "    Msg = {}".format(msg))
        
        sender = host_settings.APP_TITLE + " <noreply@" + get_application_id() + ".appspotmail.com>"
        
        mail.send_mail(sender=sender,
            to=settings.SUPPORT_EMAIL_ADDRESS,
            subject=subject,
            body=msg)
    
    except: # pylint: disable=bare-except
        logging.exception(fn_name + "Error sending support email")
        # logging.info(fn_name + "    Subject = {}".format(subject))
        # logging.info(fn_name + "    Msg = {}".format(msg))


def is_truthy(val):
    """ Returns True if val has a value that could be interpretted as True.

    An empty string returns False.

    Note that for checkbox inputs in HTML forms;
        If the field element has a value attribute specified,
            then let value be the value of that attribute;
        otherwise,
            let value be the string "on".
        If checkbox isn't checked then it doesn't contribute to the data sent on form submission.

        So when getting the checkbox value in a POST handler, if value hasn't been set
            val = self.request.get('element_name', '')
        val will be 'on' if checkbox is checked, or empty string if checkbox is unchecked
    """
    
    if val is None:
        return False

    if isinstance(val, bool):
        return val

    try:
        return val.lower() in ['true', 'yes', 'y', 't', 'on', 'enable', 'enabled', 'checked', '1']
    except: # pylint: disable=bare-except
        logging.warning("Unable to parse '%s', so returning False", str(val))
        return False


def is_dev_server():
    """ Returns True if app is running on the development server.

    Note that according to
        Detecting application runtime environment
    at
        https://cloud.google.com/appengine/docs/python/tools/using-local-server

    "To find out whether your code is running in production or in the local development server, check if os.getenv('SERVER_SOFTWARE', '').startswith('Google App Engine/').
    When this is True, you're running in production; otherwise, you're running in the local development server."

    I am checking for "Dev" in case Google decides to change the name of GAE.

    """
    server_software = os.environ.get('SERVER_SOFTWARE', '')
    return server_software.startswith('Dev')


def data_is_encrypted(tasks_backup_job):
    """ Returns True if the tasks data has been encrypted.
    
        This assumes that the worker stores the encrypted AES key in
            tasks_backup_job.encrypted_aes_key_b64
        when the tasks are encrypted.
        
        This will return False for any backup old jobs, which were created before GTB implemented
        encryption of tasks data, as those job records won't have an 'encrypted_aes_key_b64'
        property, or the property will be ''.
    """
    
    try:
        if tasks_backup_job.encrypted_aes_key_b64:
            return True
    except: # pylint: disable=bare-except
        return False # Probably an old job record, which doesn't have the encrypted_aes_key_b64 property
    return False # No AES key, so the data hasn't been encrypted


def encryption_keys_are_valid(private_key_b64, tasks_backup_job): # pylint: disable=too-many-return-statements
    """ Returns True if the encrypted AES key can be decrypted by the private RSA key.
    
        Returns False if;
            either key doesn't have a value, OR
            the strings are not valid Base64 strings
    
        If the RSA private key doesn't match the public key used to encrypt the AES key, attempting
        to decrypt the encrypted AES key raises a "ValueError: Incorrect decryption"
    """
    
    fn_name = "encryption_keys_are_valid(): "
    
    if not tasks_backup_job:
        # A job record must be supplied
        logging.debug("%sFALSE: No tasks_backup_job", fn_name)
        return False
    
    # Both keys need to be set
    if not private_key_b64:
        logging.debug("%sFALSE: No private key", fn_name)
        return False
        
    if not tasks_backup_job.encrypted_aes_key_b64:
        logging.debug("%sFALSE: No encrypted AES key", fn_name)
        return False

    try:
        # This will fail if private_key_b64 is not a Base64-encoded RSA key, the most likely
        # cause is that the user has edited the cookie
        rsa_decrypt_key = RSA.importKey(base64.b64decode(private_key_b64))
        if not rsa_decrypt_key.has_private():
            # The key is not a private key
            logging.debug("%sFALSE: Not a private RSA key", fn_name)
            return False
            
        rsa_decrypt_cipher = PKCS1_OAEP.new(rsa_decrypt_key)
        
        encrypted_aes_key = base64.b64decode(tasks_backup_job.encrypted_aes_key_b64)
        
        # This will raise "ValueError: Incorrect decryption" if the private key doesn't
        # match the public key used to encrypt the AES key.
        aes_key = rsa_decrypt_cipher.decrypt(encrypted_aes_key) # pylint: disable=unused-variable
        logging.debug("%sTRUE: Encrypted AES key matches RSA private key", fn_name)
        return True
    
    except ValueError as ve: # pylint: disable=invalid-name
        logging.debug("%sFALSE: Keys don't match\n" +
            "Unable to decrypt AES key using supplied RSA private key\n" +
            "%s",
            fn_name, get_exception_msg(ve))
        return False
        
    except: # pylint: disable=bare-except
        logging.exception("%sFALSE: Error attempting to decrypt AES key with RSA private key", 
            fn_name)
        return False


def results_can_be_returned(self, tasks_backup_job):
    """ Returns True if the results can be returned to the user.
    
        Returns True if:
            - Tasks are not encrypted, OR
            - Tasks are encrypted, and the keys all match
    """
    
    fn_name = "results_can_be_returned(): "
    
    if not tasks_backup_job:
        logging.error("%sFALSE: No job record", fn_name)
        return False
    
    if tasks_backup_job.status != constants.ExportJobStatus.EXPORT_COMPLETED:
        logging.error("%sFALSE: Job not completed; Status = '%s'", fn_name, tasks_backup_job.status)
        return False
    
    if not data_is_encrypted(tasks_backup_job):
        logging.debug("%sTRUE: Data is not encrypted", fn_name)
        return True
        
    private_key_b64 = self.request.cookies.get('private_key_b64', '')
        
    if encryption_keys_are_valid(private_key_b64, tasks_backup_job):
        logging.debug("%sTRUE: Encryption keys are valid", fn_name)
        return True
        
    logging.error("%sFALSE: Encryption keys are not valid", fn_name)
    return False



def get_aes_decrypt_cipher(private_key_b64, tasks_backup_job):
    """ Returns an AES decryprion cypher, which can be used to decrypt the user's encrypted tasks.
    
        Raises
        ------
        GtbDecryptionError
            If an AES encryption cypher could not be created
    """
    
    fn_name = "get_aes_decrypt_cipher(): "
    
    if not tasks_backup_job:
        # A job record must be supplied
        logging.warning("%sNo tasks_backup_job", fn_name)
        raise GtbDecryptionError("No tasks_backup_job")
    
    # Both keys need to be set
    if not private_key_b64:
        logging.warning("%sNo private key", fn_name)
        raise GtbDecryptionError("No private key")
        
    if not tasks_backup_job.encrypted_aes_key_b64:
        logging.warning("%sNo encrypted AES key", fn_name)
        raise GtbDecryptionError("No encrypted AES key")

    try:
        # This will fail if private_key_b64 is not a Base64-encoded RSA key, the most likely
        # cause is that the user has edited the cookie
        rsa_decrypt_key = RSA.importKey(base64.b64decode(private_key_b64))
        if not rsa_decrypt_key.has_private():
            # The key is not a private key
            logging.warning("%sRSA key is not a private RSA key", fn_name)
            raise GtbDecryptionError("RSA key is not a private RSA key")
            
        rsa_decrypt_cipher = PKCS1_OAEP.new(rsa_decrypt_key)
        
        encrypted_aes_key = base64.b64decode(tasks_backup_job.encrypted_aes_key_b64)
        
        # This will raise "ValueError: Incorrect decryption" if the private key doesn't
        # match the public key used to encrypt the AES key.
        aes_key = rsa_decrypt_cipher.decrypt(encrypted_aes_key) # pylint: disable=unused-variable
        aes_decrypt_cipher = AES.new(aes_key, AES.MODE_CTR, counter=Counter.new(128))
        logging.debug("%sReturning AES decrypt cypher", fn_name)
        return aes_decrypt_cipher
    
    except ValueError as ve: # pylint: disable=invalid-name
        logging.exception("%sUnable to decrypt AES key using RSA private key", fn_name)
        raise GtbDecryptionError("Keys don't match. Unable to decrypt AES key using RSA private key: " +
            get_exception_msg(ve))
        
    except Exception as ex: # pylint: disable=broad-except
        logging.exception("%sError attempting to decrypt AES key with RSA private key", fn_name)
        raise GtbDecryptionError("Error attempting to decrypt AES key with RSA private key: " +
            get_exception_msg(ex))

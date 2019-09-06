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

import Cookie
import cgi
import sys
import os
import traceback
import logging
import datetime
from urlparse import urljoin
import unicodedata


from google.appengine.api import logservice # To flush logs
from google.appengine.api import mail
from google.appengine.api import urlfetch
from google.appengine.api.app_identity import get_application_id
from google.appengine.ext.webapp import template


# Project-specific imports
import settings
import constants
import appversion # appversion.version is set before the upload process to keep the version number consistent
import host_settings


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
    
    
def serve_message_page(self, 
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
        if custom_button_url == settings.MAIN_PAGE_URL:
            # Relative URLs sometimes fail on Firefox, so convert the default relative URL to an absolute URL
            custom_button_url = urljoin("https://" + self.request.host, settings.MAIN_PAGE_URL)
    
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
                    
                    
def format_datetime_as_str(dt, format_str, date_only=False, prefix=''):
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
    
    
def since_msg(job_start_timestamp):
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
    
    
def send_email_to_support(subject, msg):
    fn_name = "send_email_to_support: "
    
    try:
        # TODO: Add date & time (or some random, unique ID) to subject so each subject is unique,
        # so that Gmail doesn't put them all in one conversation
        subject=host_settings.APP_TITLE + u" ERROR - " + subject
        
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

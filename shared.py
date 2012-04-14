import cgi

import settings
import logging
from google.appengine.api import logservice # To flush logs

logservice.AUTOFLUSH_EVERY_SECONDS = 5
logservice.AUTOFLUSH_EVERY_BYTES = None
logservice.AUTOFLUSH_EVERY_LINES = 5
logservice.AUTOFLUSH_ENABLED = True

# Shared functions
# Can't use the name common, because there is already a module named common


def GetSettings(hostname):
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
  
    if settings.client_ids.has_key(hostname):
        client_id = settings.client_ids[hostname]
    else:
        client_id = None
        raise KeyError("No ID entry in settings module for host = %s" % hostname)
  
    if settings.client_secrets.has_key(hostname):
        client_secret = settings.client_secrets[hostname]
    else:
        client_secret = None
        raise KeyError("No secret entry in settings module for host = %s" % hostname)
  
    if hasattr(settings, 'user_agents') and settings.user_agents.has_key(hostname):
        user_agent = settings.user_agents[hostname]
    else:
        user_agent = settings.DEFAULT_USER_AGENT

    if hasattr(settings, 'app_titles') and settings.app_titles.has_key(hostname):
        app_title = settings.app_titles[hostname]
    else:
        app_title = settings.DEFAULT_APP_TITLE
        
    if hasattr(settings, 'product_name') and settings.product_name.has_key(client_id):
        product_name = settings.app_titles[client_id]
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
  

def DumpObj(obj):
    for attr in dir(obj):
        logging.debug("    obj.%s = %s" % (attr, getattr(obj, attr)))
    logservice.flush()

    
def EscapeHtml(text):
    """Ensure that text is properly escaped as valid HTML"""
    if text is None:
        return None
    return cgi.escape(text).encode('ascii', 'xmlcharrefreplace')
    #return "".join(html_escape_table.get(c,c) for c in text)

    
# TODO: Untested
# def runningOnDev():
    # """ Returns true when running on local dev server. """
    # return os.environ['SERVER_SOFTWARE'].startswith('Dev')

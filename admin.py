# -*- coding: utf-8 -*-
#
# Copyright 2012 Julie Smith  All Rights Reserved.
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

"""Web application handler for admin tasks"""

__author__ = "julie.smith.1999@gmail.com (Julie Smith)"

import logging
import os
import sys
import cgi
import pickle
import datetime

import webapp2


from google.appengine.ext import db
from google.appengine.ext.webapp import template
from google.appengine.runtime import apiproxy_errors
from google.appengine.runtime import DeadlineExceededError
from google.appengine.api import urlfetch_errors
from google.appengine.api import logservice # To flush logs
from google.appengine.api.app_identity import get_application_id

import httplib2
from oauth2client.appengine import OAuth2Decorator

logservice.AUTOFLUSH_EVERY_SECONDS = 5
logservice.AUTOFLUSH_EVERY_BYTES = None
logservice.AUTOFLUSH_EVERY_LINES = 5
logservice.AUTOFLUSH_ENABLED = True


# Application-specific imports
import model
import settings
import appversion # appversion.version is set before the upload process to keep the version number consistent
import shared # Code which is common between tasks-backup.py and worker.py
import constants
import host_settings


msg = "Authorisation error. Please report this error to " + settings.url_issues_page

auth_decorator = OAuth2Decorator(client_id=host_settings.CLIENT_ID,
                                 client_secret=host_settings.CLIENT_SECRET,
                                 scope=host_settings.SCOPE,
                                 user_agent=host_settings.USER_AGENT,
                                 message=msg)
                            
                            
  
    
class DownloadStatsHandler(webapp2.RequestHandler):
    """Returns statistics as a CSV file"""

    @auth_decorator.oauth_required
    def get(self):

        fn_name = "DisplayStatsHandler.get(): "

        logging.debug(fn_name + "<Start> (app version %s)" % appversion.version )
        logservice.flush()
        
        stats_query = model.UsageStats.all()
        # stats_query.order('start_time')
        # stats_query.order('user_hash')
        stats = stats_query.run()
        
        try:
            stats_filename = "stats_" + get_application_id() + "_" + datetime.datetime.now().strftime("%Y-%m-%d") + ".csv"
              
            template_values = {'stats' : stats}
            self.response.headers["Content-Type"] = "text/csv"
            self.response.headers.add_header(
                "Content-Disposition", "attachment; filename=%s" % stats_filename)

                               
            path = os.path.join(os.path.dirname(__file__), constants.PATH_TO_TEMPLATES, "stats.csv")
            self.response.out.write(template.render(path, template_values))
            logging.debug(fn_name + "<End>" )
            logservice.flush()
            
        except Exception, e:
            logging.exception(fn_name + "Caught top-level exception")
            
            self.response.headers["Content-Type"] = "text/html; charset=utf-8"
            try:
                # Clear "Content-Disposition" so user will see error in browser.
                # If not removed, output goes to file (if error generated after "Content-Disposition" was set),
                # and user would not see the error message!
                del self.response.headers["Content-Disposition"]
            except Exception, e1:
                logging.debug(fn_name + "Unable to delete 'Content-Disposition' from headers (may not be a problem, because header may not have had it set): " + shared.get_exception_msg(e1))
            self.response.clear() 
            
            self.response.out.write("""Oops! Something went terribly wrong.<br />%s<br />Please report this error to <a href="http://code.google.com/p/tasks-backup/issues/list">code.google.com/p/tasks-backup/issues/list</a>""" % shared.get_exception_msg(e))
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()
    
    

app = webapp2.WSGIApplication(
    [
        ('/admin/stats', DownloadStatsHandler),
    ], debug=False)        


#!/usr/bin/python2.5
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

from google.appengine.dist import use_library
use_library("django", "1.2")

import logging
import os
import sys
import cgi
import pickle
import datetime

from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp import util
from google.appengine.runtime import apiproxy_errors
from google.appengine.runtime import DeadlineExceededError
from google.appengine.api import urlfetch_errors
from google.appengine.api import logservice # To flush logs
from google.appengine.api.app_identity import get_application_id


logservice.AUTOFLUSH_EVERY_SECONDS = 5
logservice.AUTOFLUSH_EVERY_BYTES = None
logservice.AUTOFLUSH_EVERY_LINES = 5
logservice.AUTOFLUSH_ENABLED = True


import model
import settings
import appversion # appversion.version is set before the upload process to keep the version number consistent
import shared # Code whis is common between tasks-backup.py and worker.py
import constants

  
    
class DownloadStatsHandler(webapp.RequestHandler):
    """Display statistics"""

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
            except Exception, e:
                logging.debug(fn_name + "Unable to delete 'Content-Disposition' from headers: " + shared.get_exception_msg(e))
            self.response.clear() 
            
            self.response.out.write("""Oops! Something went terribly wrong.<br />%s<br />Please report this error to <a href="http://code.google.com/p/tasks-backup/issues/list">code.google.com/p/tasks-backup/issues/list</a>""" % shared.get_exception_msg(e))
            logging.debug(fn_name + "<End> due to exception" )
            logservice.flush()
    
    


        

def real_main():
    logging.debug("main(): Starting tasks-backup (app version %s)" %appversion.version)
    template.register_template_library("common.customdjango")

    application = webapp.WSGIApplication(
        [
            ('/admin/stats', DownloadStatsHandler),
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

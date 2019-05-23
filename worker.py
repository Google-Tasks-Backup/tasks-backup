# -*- coding: utf-8 -*-
#
# Copyright 2012 Julie Smith.  All Rights Reserved.
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

"""Worker to retrieve tasks from Google Tasks server.

    This worker is started by a taskqueue from tasks_backup
"""

__author__ = "julie.smith.1999@gmail.com (Julie Smith)"

import logging
import pickle
import datetime
import time
import math
import json

import webapp2

from google.appengine.api import urlfetch
from google.appengine.api import urlfetch_errors
from google.appengine.api import logservice # To flush logs
from google.appengine.ext import db
from google.appengine.runtime import apiproxy_errors
from google.appengine.runtime import DeadlineExceededError


import httplib2

# OLD (pre google-api-python-client-gae-1.0)
# from oauth2client import appengine
# from oauth2client import client

# JS 2012-09-16: Imports to enable credentials = StorageByKeyName()
from oauth2client.appengine import StorageByKeyName
from oauth2client.appengine import CredentialsModel

# To allow catching initial "error" : "invalid_grant" and logging as Info
# rather than as a Warning or Error, because AccessTokenRefreshError seems
# to happen quite regularly
from oauth2client.client import AccessTokenRefreshError

from apiclient import discovery
from apiclient import errors as apiclient_errors

import model
import settings
import appversion # appversion.version is set before the upload process to keep the version number consistent
import shared # Code whis is common between tasks-backup.py and worker.py
from shared import DailyLimitExceededError
import constants


logservice.AUTOFLUSH_EVERY_SECONDS = 5
logservice.AUTOFLUSH_EVERY_BYTES = None
logservice.AUTOFLUSH_EVERY_LINES = 5
logservice.AUTOFLUSH_ENABLED = True



# Fix for DeadlineExceeded, because "Pre-Call Hooks to UrlFetch Not Working"
#     Based on code from https://groups.google.com/forum/#!msg/google-appengine/OANTefJvn0A/uRKKHnCKr7QJ
real_fetch = urlfetch.fetch # pylint: disable=invalid-name
def fetch_with_deadline(url, *args, **argv):
    argv['deadline'] = settings.URL_FETCH_TIMEOUT
    return real_fetch(url, *args, **argv)
urlfetch.fetch = fetch_with_deadline




# Orig __author__ = "dwightguth@google.com (Dwight Guth)"
__author__ = "julie.smith.1999@gmail.com (Julie Smith)"



class ProcessTasksWorker(webapp2.RequestHandler):
    """ Process tasks according to data in the ProcessTasksJob entity """

    credentials = None
    user_email = None
    is_test_user = False
    process_tasks_job = None
    tasks_svc = None
    tasklists_svc = None
    
    def _log_progress(self, prefix_msg=""):
        fn_name = "_log_progress: "
        
        if prefix_msg:
            logging.debug(fn_name + prefix_msg + " - Job status = '" + str(self.process_tasks_job.status) + 
                "', progress: " + str(self.process_tasks_job.total_progress))
        else:
            logging.debug(fn_name + "Job status = '" + str(self.process_tasks_job.status) + 
                "', progress: " + str(self.process_tasks_job.total_progress))
                
        if self.process_tasks_job.message:
            logging.debug(fn_name + "Message = " + str(self.process_tasks_job.message))
            
        if self.process_tasks_job.error_message:
            logging.debug(fn_name + "Error message = " + str(self.process_tasks_job.error_message))

        logservice.flush()
        
    
    def post(self):
        fn_name = "ProcessTasksWorker.post(): "
        
        logging.debug(fn_name + "<start> (app version %s)" %appversion.version)
        logservice.flush()

        self.prev_progress_timestamp = datetime.datetime.now() # pylint: disable=attribute-defined-outside-init
        
        self.user_email = self.request.get(settings.TASKS_QUEUE_KEY_NAME)
        
        self.is_test_user = shared.is_test_user(self.user_email)
        
        if self.user_email:
            
            # Retrieve the DB record for this user
            self.process_tasks_job = model.ProcessTasksJob.get_by_key_name(self.user_email)
            
            if self.process_tasks_job is None:
                logging.error(fn_name + "No DB record for " + self.user_email)
                logservice.flush()
                logging.debug(fn_name + "<End> No DB record")
                # TODO: Find some way of notifying the user?????
                # Could use memcache to relay a message which is displayed in ProgressHandler
                return
                
                
        
            logging.debug(fn_name + "Retrieved process tasks job for " + str(self.user_email))
            logging.debug(fn_name + "Job was requested at " + str(self.process_tasks_job.job_created_timestamp))
            logservice.flush()
            
            if self.process_tasks_job.status != constants.ExportJobStatus.TO_BE_STARTED:
                # Very occassionally, GAE starts a 2nd instance of the worker, so we check for that here.
                
                # Check when job status was last updated. If it was less than settings.MAX_JOB_PROGRESS_INTERVAL
                # seconds ago, assume that another instance is already running, log error and exit
                time_since_last_update = datetime.datetime.now() - self.process_tasks_job.job_progress_timestamp
                if time_since_last_update.seconds < settings.MAX_JOB_PROGRESS_INTERVAL:
                    logging.error(fn_name + "It appears that worker was called whilst another job is already running for " + str(self.user_email))
                    logging.error(fn_name + "Previous job requested at " + str(self.process_tasks_job.job_created_timestamp) + " UTC is still running.")
                    logging.error(fn_name + "Previous worker started at " + str(self.process_tasks_job.job_start_timestamp) + " UTC and last job progress update was " + str(time_since_last_update.seconds) + " seconds ago, with status " + str(self.process_tasks_job.status) )
                    logging.warning(fn_name + "<End> (Another worker is already running)")
                    logservice.flush()
                    return
                
                else:
                    # A previous job hasn't completed, and hasn't updated progress for more than 
                    # settings.MAX_JOB_PROGRESS_INTERVAL secons, so assume that previous worker
                    # for this job has died.
                    logging.error(fn_name + "It appears that a previous job requested by " + str(self.user_email) + " at " + str(self.process_tasks_job.job_created_timestamp) + " UTC has stalled.")
                    logging.error(fn_name + "Previous worker started at " + str(self.process_tasks_job.job_start_timestamp) + " UTC and last job progress update was " + str(time_since_last_update.seconds) + " seconds ago, with status " + str(self.process_tasks_job.status) + ", progress = ")
                    
                    if self.process_tasks_job.number_of_job_starts > settings.MAX_NUM_JOB_STARTS:
                        logging.error(fn_name + "This job has already been started " + str(self.process_tasks_job.number_of_job_starts) + " times. Giving up")
                        logging.warning(fn_name + "<End> (Multiple job restart failures)")
                        logservice.flush()
                        return
                    else:
                        logging.info(fn_name + "Attempting to restart backup job. Attempt number " + 
                            str(self.process_tasks_job.number_of_job_starts + 1))
                        logservice.flush()
            
            
            self.process_tasks_job.status = constants.ExportJobStatus.INITIALISING
            self.process_tasks_job.number_of_job_starts = self.process_tasks_job.number_of_job_starts + 1
            self.process_tasks_job.job_progress_timestamp = datetime.datetime.now()
            self.process_tasks_job.job_start_timestamp = datetime.datetime.now()
            self.process_tasks_job.message = "Validating background job ..."
            self._log_progress("Initialising")
            self.process_tasks_job.put()

            time_since_job_request = datetime.datetime.now() - self.process_tasks_job.job_created_timestamp
            logging.debug(fn_name + "Starting job that was requested " + str(time_since_job_request.seconds) + 
                " seconds ago at " + str(self.process_tasks_job.job_created_timestamp) + " UTC")
            
            
            user = self.process_tasks_job.user
            if not user:
                logging.error(fn_name + "No user object in DB record for " + str(self.user_email))
                logservice.flush()
                self.process_tasks_job.status = constants.ExportJobStatus.ERROR
                self.process_tasks_job.message = ''
                self.process_tasks_job.error_message = "Problem with user details. Please restart."
                self.process_tasks_job.job_progress_timestamp = datetime.datetime.now()
                self._log_progress("No user")
                self.process_tasks_job.put()
                logging.debug(fn_name + "<End> No user object")
                return
                  
            # self.credentials = self.process_tasks_job.credentials
            
            # DEBUG: 2012-09-16; Trying a different method of retrieving credentials, to see if it
            # allows retrieveal of credentials for TAFE account
            self.credentials = StorageByKeyName(CredentialsModel, user.user_id(), 'credentials').get()
            
            if not self.credentials:
                logging.error(fn_name + "No credentials in DB record for " + str(self.user_email))
                logservice.flush()
                self.process_tasks_job.status = constants.ExportJobStatus.ERROR
                self.process_tasks_job.message = ''
                self.process_tasks_job.error_message = "Problem with user credentials. Please restart."
                self.process_tasks_job.job_progress_timestamp = datetime.datetime.now()
                self._log_progress("No credentials")
                self.process_tasks_job.put()
                logging.debug(fn_name + "<End> No credentials")
                return
          
            if self.credentials.invalid:
                logging.error(fn_name + "Invalid credentials in DB record for " + str(self.user_email))
                logservice.flush()
                self.process_tasks_job.status = constants.ExportJobStatus.ERROR
                self.process_tasks_job.message = ''
                self.process_tasks_job.error_message = "Invalid credentials. Please restart and re-authenticate."
                self.process_tasks_job.job_progress_timestamp = datetime.datetime.now()
                self._log_progress("Credentials invalid")
                logservice.flush()
                self.process_tasks_job.put()
                logging.debug(fn_name + "<End> Invalid credentials")
                return
          
            if self.is_test_user:
                logging.debug(fn_name + "User is test user %s" % self.user_email)
                logservice.flush()
                
            retry_count = settings.NUM_API_TRIES
            while retry_count > 0:
                retry_count = retry_count - 1
                # Accessing tasklists & tasks services may take some time (especially if retries due to 
                # DeadlineExceeded), so update progress so that job doesn't stall
                self._update_progress("Connecting to server ...")  # Update progress so that job doesn't stall
                try:
                    # ---------------------------------------------------------
                    #       Connect to the tasks and tasklists services
                    # ---------------------------------------------------------
                    http = httplib2.Http()
                    http = self.credentials.authorize(http)
                    service = discovery.build("tasks", "v1", http=http)
                    self.tasklists_svc = service.tasklists() # pylint: disable=no-member
                    self.tasks_svc = service.tasks() # pylint: disable=no-member

                    # This will also throw DailyLimitExceededError BEFORE processing starts if no quota available.
                    logging.debug(fn_name + "DEBUG: Retrieving dummy list of tasklists, to 'prep' the service")
                    dummy_list = self.tasklists_svc.list().execute()
                    
                    break # Success, so break out of the retry loop

                except apiclient_errors.HttpError as http_err:
                    self._handle_http_error(fn_name, http_err, retry_count, "Error connecting to Tasks services")
                    
                except Exception as ex: # pylint: disable=broad-except
                    self._handle_general_error(fn_name, ex, retry_count, "Error connecting to Tasks services")
            
            
            # =========================================
            #   Retrieve tasks from the Google server
            # =========================================
            self._export_tasks()

        else:
            logging.error(fn_name + "No processing, as there was no user_email key")
            logservice.flush()
            
        logging.debug(fn_name + "<End>")
        logservice.flush()


    def _export_tasks(self):
    
        fn_name = "_export_tasks: "
        
        logging.debug(fn_name + "<Start>")
        logservice.flush()
        
        start_time = datetime.datetime.now()
        
        include_hidden = self.process_tasks_job.include_hidden
        include_completed = self.process_tasks_job.include_completed
        include_deleted = self.process_tasks_job.include_deleted
        
        summary_msg = ''
        
        # Retrieve all tasks for the user
        try:
            logging.debug(fn_name + 
                "include_completed = " + str(include_completed) +
                ", include_hidden = " + str(include_hidden) +
                ", include_deleted = " + str(include_deleted))
            logservice.flush()
            
            
            # ##############################################
            # FLOW
            # ----------------------------------------------
            # For each page of taskslists
            #   For each tasklist
            #     For each page of tasks
            #       For each task
            #         Fix date format
            #       Add tasks to tasklist collection
            #     Add tasklist to tasklists collection
            # Use tasklists collection to return tasks backup to user
            
            self.process_tasks_job.status = constants.ExportJobStatus.BUILDING
            self.process_tasks_job.job_progress_timestamp = datetime.datetime.now()
            self.process_tasks_job.message = 'Retrieving tasks from server ...'
            self._log_progress("Building")
            self.process_tasks_job.put()
            
            # This list will contain zero or more tasklist dictionaries, which each contain tasks
            tasklists = [] 
            
            total_num_tasklists = 0
            total_num_tasks = 0
            tasks_per_list = []
            
            # ---------------------------------------
            # Retrieve all the tasklists for the user
            # ---------------------------------------
            logging.debug(fn_name + "Retrieve all the tasklists for the user")
            logservice.flush()
            next_tasklists_page_token = None
            more_tasklists_data_to_retrieve = True
            while more_tasklists_data_to_retrieve:
                if self.is_test_user:
                    logging.debug(fn_name + "calling tasklists.list().execute() to create tasklists list")
                    logservice.flush()
            
                retry_count = settings.NUM_API_TRIES
                while retry_count > 0:
                    retry_count = retry_count - 1
                    try:
                        if next_tasklists_page_token:
                            tasklists_data = self.tasklists_svc.list(pageToken=next_tasklists_page_token).execute()
                        else:
                            tasklists_data = self.tasklists_svc.list().execute()
                            
                        # Successfully retrieved data, so break out of retry loop
                        break
                    

                    except apiclient_errors.HttpError as http_err:
                        self._handle_http_error(fn_name, http_err, retry_count, "Error retrieving list of tasklists")
                        
                    except Exception as ex: # pylint: disable=broad-except
                        self._handle_general_error(fn_name, ex, retry_count, "Error retrieving list of tasklists")
                      
                if self.is_test_user and settings.DUMP_DATA:
                    logging.debug(fn_name + "tasklists_data ==>")
                    logging.debug(tasklists_data)
                    logservice.flush()

                if tasklists_data.has_key(u'items'):
                  tasklists_list = tasklists_data[u'items']
                else:
                  # If there are no tasklists, then there will be no 'items' element. This could happen if
                  # the user has deleted all their tasklists. Not sure if this is even possible, but
                  # checking anyway, since it is possible to have a tasklist without 'items' (see issue #9)
                  logging.debug(fn_name + "User has no tasklists.")
                  logservice.flush()
                  tasklists_list = []
              
                # tasklists_list is a list containing the details of the user's tasklists. 
                # We are only interested in the title
              
                # if self.is_test_user and settings.DUMP_DATA:
                    # logging.debug(fn_name + "tasklists_list ==>")
                    # logging.debug(tasklists_list)


                # ---------------------------------------
                # Process all the tasklists for this user
                # ---------------------------------------
                for tasklist_data in tasklists_list:
                    total_num_tasklists = total_num_tasklists + 1
                  
                    if self.is_test_user and settings.DUMP_DATA:
                        logging.debug(fn_name + "tasklist_data ==>")
                        logging.debug(tasklist_data)
                        logservice.flush()
                  
                    # Example of a tasklist entry;
                        # u'id': u'MDAxNTkzNzU0MzA0NTY0ODMyNjI6MDow',
                        # u'kind': u'tasks#taskList',
                        # u'selfLink': u'https://www.googleapis.com/tasks/v1/users/@me/lists/MDAxNTkzNzU0MzA0NTY0ODMyNjI6MDow',
                        # u'title': u'Default List',
                        # u'updated': u'2012-01-28T07:30:18.000Z'},
               
                    tasklist_title = tasklist_data[u'title']
                    tasklist_id = tasklist_data[u'id']
                  
                    if self.is_test_user and settings.DUMP_DATA:
                        logging.debug(fn_name + "Process all the tasks in " + str(tasklist_title))
                        logservice.flush()
                            
                    # =====================================================
                    #       Process all the tasks in this task list
                    # =====================================================
                    tasklist_dict, num_tasks = self._get_tasks_in_tasklist(tasklist_title, tasklist_id, 
                        include_hidden, include_completed, include_deleted)
                    # Track number of tasks per tasklist
                    tasks_per_list.append(num_tasks)
                    
                    total_num_tasks = total_num_tasks + num_tasks
                    self.process_tasks_job.total_progress = total_num_tasks
                    self.process_tasks_job.tasklist_progress = 0 # Because total_progress now includes num_tasks for current tasklist
                    self.process_tasks_job.job_progress_timestamp = datetime.datetime.now()
                    self.process_tasks_job.message = ''
                    self._log_progress("Processed tasklist")
                    self.process_tasks_job.put()
                    
                    # if self.is_test_user:
                        # logging.debug(fn_name + "Adding %d tasks to tasklist" % len(tasklist_dict[u'tasks']))
                        
                    # Add the data for this tasklist (including all the tasks) into the collection of tasklists
                    tasklists.append(tasklist_dict)
              
                # Check if there is another page of tasklists to be retrieved
                if tasklists_data.has_key('nextPageToken'):
                    # There is another page of tasklists to be retrieved for this user, 
                    # which we'll retrieve next time around the while loop.
                    # This happens if there is more than 1 page of tasklists.
                    # It seems that each page contains 20 tasklists.
                    more_tasklists_data_to_retrieve = True # Go around while loop again
                    next_tasklists_page_token = tasklists_data['nextPageToken']
                    # if self.is_test_user:
                        # logging.debug(fn_name + "There is (at least) one more page of tasklists to be retrieved")
                else:
                    # This is the last (or only) page of results (list of tasklists)
                    more_tasklists_data_to_retrieve = False
                    next_tasklists_page_token = None
                  
            # *** end while more_tasks_data_to_retrieve ***
            
            # ------------------------------------------------------
            #   Store the data, so we can return it to the user
            # ------------------------------------------------------
              

            #   tasklists is a list of tasklist structures
            #
            #   structure of tasklist
            #   { 
            #       "title" : tasklist.title,        # Name of this tasklist
            #       "tasks"  : [ task ]              # List of task items in this tasklist
            #   }
            #
            #   structure of task
            #   {
            #       "title" : title, # Free text
            #       "status" : status, # "completed" | "needsAction"
            #       "id" : id, # Used when determining parent-child relationships
            #       "parent" : parent, # OPT: ID of the parent of this task (only if this is a sub-task)
            #       "notes" : notes, # OPT: Free text
            #       "due" : due, # OPT: Date due, e.g. 2012-01-30T00:00:00.000Z NOTE time = 0
            #       "updated" : updated, # Timestamp, e.g., 2012-01-26T07:47:18.000Z
            #       "completed" : completed # Timestamp, e.g., 2012-01-27T10:38:56.000Z
            #   }

            
            # Delete existing backup data records
            tasklist_data_records = model.TasklistsData.gql("WHERE ANCESTOR IS :1",
                                                        db.Key.from_path(settings.DB_KEY_TASKS_BACKUP_DATA, self.user_email))

            num_records = tasklist_data_records.count()
            logging.debug(fn_name + "Deleting " + str(num_records) + " old blobs")
            logservice.flush()
            
            for tasklists_data_record in tasklist_data_records:
                tasklists_data_record.delete()

            
            # logging.debug(fn_name + "Pickling tasks data ...")
            pickled_tasklists = pickle.dumps(tasklists)
            # logging.debug(fn_name + "Pickled data size = " + str(len(pickled_tasklists)))
            data_len = len(pickled_tasklists)
            
            # Multiply by 1.0 float value so that we can use ceiling to find number of Blobs required
            num_of_blobs = int(math.ceil(data_len * 1.0 / constants.MAX_BLOB_SIZE))
            logging.debug(fn_name + "Calculated " + str(num_of_blobs) + " blobs required to store " + 
                str(data_len) + " bytes")
            logservice.flush()
            
            try:
                for i in range(num_of_blobs):
                    # Write backup data records
                    tasklist_rec = model.TasklistsData(db.Key.from_path(settings.DB_KEY_TASKS_BACKUP_DATA, self.user_email))
                    slice_start = int(i*constants.MAX_BLOB_SIZE)
                    slice_end = int((i+1)*constants.MAX_BLOB_SIZE)
                    # logging.debug(fn_name + "Creating part " + str(i+1) + " of " + str(num_of_blobs) + 
                        # " using slice " + str(slice_start) + " to " + str(slice_end))
                    
                    pkl_part = pickled_tasklists[slice_start : slice_end]
                    tasklist_rec.pickled_tasks_data = pkl_part
                    tasklist_rec.idx = i
                    tasklist_rec.put()
                    
                # logging.debug(fn_name + "Marking backup job complete")
                end_time = datetime.datetime.now()
                process_time = end_time - start_time
                proc_time_str = str(process_time.seconds) + "." + str(process_time.microseconds)[:3] + " seconds"
                
                # Mark backup completed
                summary_msg = "Retrieved %d tasks from %d tasklists" % (total_num_tasks, total_num_tasklists)
                breakdown_msg = "Tasks per list: " + str(tasks_per_list)
                
                self.process_tasks_job.status = constants.ExportJobStatus.EXPORT_COMPLETED
                self.process_tasks_job.job_progress_timestamp = datetime.datetime.now()
                # self.process_tasks_job.message = summary_msg + " in " + proc_time_str
                self.process_tasks_job.message = summary_msg + " at " + \
                    start_time.strftime("%H:%M UTC, %a %d %b %Y")
                logging.info(fn_name + "COMPLETED: " + summary_msg + " for " + self.user_email + " in " + proc_time_str)
                logservice.flush()
                self.process_tasks_job.put()
                
                try:
                    end_time = datetime.datetime.now()
                    process_time = end_time - start_time
                    processing_time = process_time.days * 3600*24 + process_time.seconds + process_time.microseconds / 1000000.0
                    included_options_str = "Includes: Completed = %s, Deleted = %s, Hidden = %s" % (str(include_completed), str(include_deleted), str(include_hidden))
                    
                    logging.debug(fn_name + "STATS: Job started at " + str(self.process_tasks_job.job_start_timestamp) +
                        "\n    Worker started at " + str(start_time) +
                        "\n    " + summary_msg + 
                        "\n    " + breakdown_msg +
                        "\n    " + proc_time_str +
                        "\n    " + included_options_str)
                    logservice.flush()
                    
                    usage_stats = model.UsageStats(
                        user_hash = hash(self.user_email),
                        number_of_tasks = self.process_tasks_job.total_progress,
                        number_of_tasklists = total_num_tasklists,
                        tasks_per_tasklist = tasks_per_list,
                        include_completed = include_completed,
                        include_deleted = include_deleted,
                        include_hidden = include_hidden,
                        start_time = start_time,
                        processing_time = processing_time)
                    usage_stats.put()
                    logging.debug(fn_name + "Saved stats")
                    logservice.flush()
                
                except Exception: # pylint: disable=broad-except
                    logging.exception("Error saving stats")
                    logservice.flush()
                    # Don't bother doing anything else, because stats aren't critical
                
            except apiproxy_errors.RequestTooLargeError as rtl_ex:
                logging.exception(fn_name + "Error putting results in DB - Request too large")
                logservice.flush()
                self.process_tasks_job.status = constants.ExportJobStatus.ERROR
                self.process_tasks_job.message = ''
                self.process_tasks_job.error_message = \
                    "Tasklists data is too large - Unable to store tasklists in DB: " + \
                    shared.get_exception_msg(rtl_ex)
                self.process_tasks_job.job_progress_timestamp = datetime.datetime.now()
                self._log_progress("apiproxy_errors.RequestTooLargeError")
                self.process_tasks_job.put()
            
            except Exception as ex: # pylint: disable=broad-except
                logging.exception(fn_name + "Error putting results in DB")
                logservice.flush()
                self.process_tasks_job.status = constants.ExportJobStatus.ERROR
                self.process_tasks_job.message = ''
                self.process_tasks_job.error_message = "Unable to store tasklists in DB: " + \
                    shared.get_exception_msg(ex)
                self.process_tasks_job.job_progress_timestamp = datetime.datetime.now()
                self._log_progress("Exception")
                self.process_tasks_job.put()

        except urlfetch_errors.DeadlineExceededError, url_dee:
            logging.exception(fn_name + "urlfetch_errors.DeadlineExceededError:")
            logservice.flush()
            self.process_tasks_job.status = constants.ExportJobStatus.ERROR
            self.process_tasks_job.message = ''
            self.process_tasks_job.error_message = "Server took too long to respond: " + \
                shared.get_exception_msg(url_dee)
            self.process_tasks_job.job_progress_timestamp = datetime.datetime.now()
            self._log_progress("urlfetch_errors.DeadlineExceededError")
            self.process_tasks_job.put()
      
        except apiproxy_errors.DeadlineExceededError as api_dee:
            logging.exception(fn_name + "apiproxy_errors.DeadlineExceededError:")
            logservice.flush()
            self.process_tasks_job.status = constants.ExportJobStatus.ERROR
            self.process_tasks_job.message = ''
            self.process_tasks_job.error_message = "Server took too long to respond: " + \
                shared.get_exception_msg(api_dee)
            self.process_tasks_job.job_progress_timestamp = datetime.datetime.now()
            self._log_progress("apiproxy_errors.DeadlineExceededError")
            self.process_tasks_job.put()
        
        except DeadlineExceededError as dee:
            logging.exception(fn_name + "DeadlineExceededError:")
            logservice.flush()
            self.process_tasks_job.status = constants.ExportJobStatus.ERROR
            self.process_tasks_job.message = ''
            self.process_tasks_job.error_message = "Server took too long to respond: " + \
                shared.get_exception_msg(dee)
            self.process_tasks_job.job_progress_timestamp = datetime.datetime.now()
            self._log_progress("DeadlineExceededError")
            self.process_tasks_job.put()
        
        except Exception as ex: # pylint: disable=broad-except
            logging.exception(fn_name + "Exception:") 
            logservice.flush()
            self.process_tasks_job.status = constants.ExportJobStatus.ERROR
            self.process_tasks_job.message = ''
            self.process_tasks_job.error_message = "System error: " + shared.get_exception_msg(ex)
            self.process_tasks_job.job_progress_timestamp = datetime.datetime.now()
            self._log_progress("Exception")
            self.process_tasks_job.put()
        

        logging.debug(fn_name + "<End>")
        logservice.flush()
            
    
    def _get_tasks_in_tasklist(self, tasklist_title, tasklist_id, 
                               include_hidden, include_completed, include_deleted):
        """ Returns all the tasks in the tasklist 
        
            arguments:
              tasklist_title           -- Name of the tasklist
              tasklist_id              -- ID used to retrieve tasks from this tasklist
                                          MUST match the ID returned in the tasklist data
              include_hidden           -- If true, include hidden tasks in the backup
              include_completed        -- If true, include completed tasks in the backup
              include_deleted          -- If true, include deleted tasks in the backup
              
            returns a tuple;
              two-element dictionary;
                'title' is a string, the name of the tasklist
                'tasks' is a list. Each element in the list is dictionary representing 1 task
              number of tasks
        """        
        fn_name = "CreateBackupHandler._get_tasks_in_tasklist(): "
        
        
        tasklist_dict = {} # Blank dictionary for this tasklist
        tasklist_dict[u'title'] = tasklist_title # Store the tasklist name in the dictionary
        tasklist_dict[u'id'] = tasklist_id # Store the tasklist ID in the dictionary
        
        num_tasks = 0

        more_tasks_data_to_retrieve = True
        next_tasks_page_token = None
        
        # Keep track of when last updated, to prevent excessive DB access which could exceed quota
        prev_progress_timestamp = datetime.datetime.now()
        
        if self.is_test_user and settings.DUMP_DATA:
            logging.debug(fn_name +
                              "TEST: include_completed = " + str(include_completed) +
                              ", include_hidden = " + str(include_hidden) +
                              ", include_deleted = " + str(include_deleted))
            logservice.flush()
          
        # ---------------------------------------------------------------------------
        # Retrieve the tasks in this tasklist, and store as "tasks" in the dictionary
        # ---------------------------------------------------------------------------
        while more_tasks_data_to_retrieve:
        
            retry_count = settings.NUM_API_TRIES
            while retry_count > 0:
                retry_count = retry_count - 1
                tasks_data = {}
                try:
                    # Retrieve a page of (up to 100) tasks
                    if next_tasks_page_token:
                        # Get the next page of results
                        # This happens if there are more than 100 tasks in the list
                        # See http://code.google.com/apis/tasks/v1/using.html#api_params
                        #     "Maximum allowable value: maxResults=100"
                        tasks_data = self.tasks_svc.list(tasklist = tasklist_id, pageToken=next_tasks_page_token, 
                            showHidden=include_hidden, showCompleted=include_completed, showDeleted=include_deleted).execute()
                    else:
                        # Get the first (or only) page of results for this tasklist
                        tasks_data = self.tasks_svc.list(tasklist = tasklist_id, 
                            showHidden=include_hidden, showCompleted=include_completed, showDeleted=include_deleted).execute()
                            
                    # Succeeded, so break out of the retry loop
                    break
                
                except apiclient_errors.HttpError as http_err:
                    tasks_data = {}
                    self._handle_http_error(fn_name, http_err, retry_count, "Error retrieving list of tasks")
                    
                except Exception as ex: # pylint: disable=broad-except
                    tasks_data = {}
                    self._handle_general_error(fn_name, ex, retry_count, "Error retrieving list of tasks")
          
            if self.is_test_user and settings.DUMP_DATA:
                logging.debug(fn_name + "tasks_data ==>")
                logging.debug(tasks_data)
            
            if not tasks_data:
                logging.error(fn_name + "No tasks data for " + self.user_email)
            
            if not tasks_data.has_key(u'items'):
                # When using the Google Tasks webpage at https://mail.google.com/tasks/canvas, there will always
                # be at least one task in any tasklist, because when deleting the last task, a new blank task is
                # automatically created.
                # However, a third-party app (e.g., Calengoo on Android) CAN delete all the tasks in a task list,
                # which results in a tasklist without an 'items' element.
                logging.debug(fn_name + "No tasks in tasklist")
                logservice.flush()
            else:
                try:
                    tasks = tasks_data[u'items'] # Store all the tasks (List of Dict)
                except Exception as ex: # pylint: disable=broad-except
                    logging.exception(fn_name, "Exception extracting items from tasks_data: " + 
                      shared.get_exception_msg(ex))
                    #logging.error(tasks_data)
                    logservice.flush()
                    raise ex
                
                # if self.is_test_user and settings.DUMP_DATA:
                    # logging.debug(fn_name + "tasks ==>")
                    # logging.debug(tasks)
                    # logservice.flush()
                
                for task in tasks:
                    num_tasks = num_tasks + 1
                    
                    # TODO: Investigate if including this will cause memory to be exceeded for very large tasks list
                    # Store original RFC-3339 timestamps (used for raw2 export format)
                    if task.has_key('due'):
                        task['due_RFC3339'] = task['due']
                    if task.has_key('updated'):
                        task['updated_RFC3339'] = task['updated']
                    if task.has_key('completed'):
                        task['completed_RFC3339'] = task['completed']
                    
                    # Converts the RFC-3339 string returned by the server to a date or datetime object  
                    # so that other methods (such as Django templates) can display a custom formatted date
                    shared.set_timestamp(task, u'due', date_only=True)
                    shared.set_timestamp(task, u'updated')
                    shared.set_timestamp(task, u'completed')
                    
                if tasklist_dict.has_key(u'tasks'):
                    # This is the n'th page of task data for this tasklist, so extend the existing list of tasks
                    tasklist_dict[u'tasks'].extend(tasks)
                else:
                    # This is the first (or only) list of task for this tasklist
                    tasklist_dict[u'tasks'] = tasks
                
                # if self.is_test_user:
                    # logging.debug(fn_name + "Adding %d items for %s" % (len(tasks), tasklist_title))
                # else:
                    # logging.debug(fn_name + "Adding %d items to tasklist" % len(tasks))
            
            
            # ---------------------------------------------------------------------
            # Check if there is another page of data (more tasks for this tasklist)
            # ---------------------------------------------------------------------
            if tasks_data.has_key('nextPageToken'):
                # There is another page of tasks to be retrieved for this tasklist, 
                # which we'll retrieve next time around the while loop.
                # This happens if there are more than 100 tasks in the list
                # See http://code.google.com/apis/tasks/v1/using.html#api_params
                #     "Maximum allowable value: maxResults=100"
                more_tasks_data_to_retrieve = True # Go around while loop again
                next_tasks_page_token = tasks_data['nextPageToken']
                # if self.is_test_user:
                    # logging.debug(fn_name + "There is (at least) one more page of data to be retrieved")
                  
                # More than one page, so update progress
                if (datetime.datetime.now() - prev_progress_timestamp).seconds > settings.PROGRESS_UPDATE_INTERVAL:
                    self.process_tasks_job.tasklist_progress = num_tasks
                    self.process_tasks_job.job_progress_timestamp = datetime.datetime.now()
                    self.process_tasks_job.message = ''
                    logging.debug(fn_name + "Processed page of tasklists. Updated job status: '" + 
                        str(self.process_tasks_job.status) + "', updated progress = " + 
                        str(self.process_tasks_job.tasklist_progress))
                    logservice.flush()
                    self.process_tasks_job.put()
                    prev_progress_timestamp = datetime.datetime.now()
            else:
                # This is the last (or only) page of results (list of tasks) for this task lists
                # Don't need to update here if no more pages, because calling method updates
                more_tasks_data_to_retrieve = False
                next_tasks_page_token = None
              
        if self.is_test_user:
            logging.debug(fn_name + "Retrieved " + str(num_tasks) + " tasks from " + tasklist_title)
        else:
            logging.debug(fn_name + "Retrieved " + str(num_tasks) + " tasks from task list")
        logservice.flush()  
        
        return tasklist_dict, num_tasks


    def _handle_http_error(self, fn_name, ex, retry_count, err_msg):
        self._update_progress(force=True)
        
        # TODO: Find a reliable way to detect daily limit exceeded that doesn't rely on text
        if ex and ex._get_reason() and ex._get_reason().lower() == "daily limit exceeded": # pylint: disable=protected-access
            logging.warning(fn_name + "HttpError: " + err_msg + " for " + self.user_email + 
                ": " + shared.get_exception_msg(ex))
            logservice.flush()
            raise DailyLimitExceededError()
            
        if retry_count == settings.NUM_API_TRIES-1 and ex and ex.resp and ex.resp.status == 503:
            # Log first 503 as an Info level, because 
            #   (a) There are a frequent 503 errors
            #   (b) Almost all 503 errors recover after a single retry
            logging.info(fn_name + "HttpError: " + err_msg + " for " + self.user_email + 
                ": " + shared.get_exception_msg(ex) + 
                "\nFirst attempt, so logged as info. " + str(retry_count) + " attempts remaining")
            logservice.flush()
        else:
            if retry_count > 0:
                logging.warning(fn_name + "HttpError: " + err_msg + " for " + self.user_email + 
                    ": " + shared.get_exception_msg(ex) + "\n" +
                    str(retry_count) + " attempts remaining")
                logservice.flush()
            else:
                logging.exception(fn_name + "HttpError: " + err_msg + " for " + self.user_email + 
                    ": " + shared.get_exception_msg(ex) + "\n" +
                    "Giving up after " +  str(settings.NUM_API_TRIES) + " attempts")
                    
                # Try logging the content of the HTTP response, 
                # in case it contains useful info to help debug the error
                try:
                    try:
                        parsed_json = json.loads(ex.content)
                        logging.info(fn_name + "HTTP error content as JSON =\n{}".format(
                            json.dumps(parsed_json, indent=4)))
                    except: # pylint: disable=bare-except
                        logging.info(fn_name + "HTTP error content = '{}'".format(
                            ex.content))
                except: # pylint: disable=bare-except
                    pass
                    
                logservice.flush()
                self._report_error(err_msg)
                raise ex

        # Last chances - sleep to give the server some extra time before re-requesting
        if retry_count <= 2:
            logging.debug(fn_name + "Giving server an extra chance; Sleeping for " + 
                str(settings.WORKER_API_RETRY_SLEEP_DURATION) + 
                " seconds before retrying")
            logservice.flush()
            time.sleep(settings.WORKER_API_RETRY_SLEEP_DURATION)
            
            
    def _handle_general_error(self, fn_name, ex, retry_count, err_msg):
        self._update_progress(force=True)
        if retry_count > 0:
            if isinstance(ex, AccessTokenRefreshError):
                # Log first 'n' AccessTokenRefreshError as Info, because they are reasonably common,
                # and the system usually continues normally after the 2nd instance of
                # "new_request: Refreshing due to a 401"
                # Occassionally, the system seems to need a 3rd attempt 
                # (i.ex., success after waiting 45 seconds)
                logging.info(fn_name + 
                    "Access Token Refresh Error: " + err_msg + " for " + self.user_email + 
                    " (not yet an error). " + str(retry_count) + " attempts remaining: " + shared.get_exception_msg(ex))
            else:
                logging.warning(fn_name + "Error: " + err_msg + " for " + self.user_email + 
                    ": " + shared.get_exception_msg(ex) + "\n" +
                    str(retry_count) + " attempts remaining")
            logservice.flush()
        else:
            logging.exception(fn_name + "Error: " + err_msg + " for " + self.user_email + 
                ": " + shared.get_exception_msg(ex) + "\n" +
                "Giving up after " + str(settings.NUM_API_TRIES) + " attempts")
            logservice.flush()
            self._report_error(err_msg)
            raise ex

        # Last chances - sleep to give the server some extra time before re-requesting
        if retry_count <= 2:
            logging.debug(fn_name + "Giving server an extra chance; Sleeping for " + 
                str(settings.WORKER_API_RETRY_SLEEP_DURATION) + 
                " seconds before retrying")
            logservice.flush()
            time.sleep(settings.WORKER_API_RETRY_SLEEP_DURATION)
            

    def _update_progress(self, msg=None, force=False):
        """ Update progress so that job doesn't stall """
        
        if force or (datetime.datetime.now() - self.prev_progress_timestamp).seconds > settings.PROGRESS_UPDATE_INTERVAL:
            if msg:
                self.process_tasks_job.message = msg
            self.process_tasks_job.job_progress_timestamp = datetime.datetime.now()
            self._log_progress("Update progress")
            self.process_tasks_job.put()
            self.prev_progress_timestamp = datetime.datetime.now() # pylint: disable=attribute-defined-outside-init
        

    def _report_error(self, err_msg):
        """ Log error message, and update Job record to advise user of error """
        
        fn_name = "_report_error(): "
        
        self.process_tasks_job.status = constants.ExportJobStatus.ERROR
        self.process_tasks_job.message = ''

        if self.process_tasks_job.error_message:
            logging.warning(fn_name + "Existing error: " + self.process_tasks_job.error_message)
            logservice.flush()
            self.process_tasks_job.error_message += "; " + err_msg
        else:
            self.process_tasks_job.error_message = err_msg
            
        logging.warning(fn_name + "Reporting error for " + self.user_email + ": " + 
            self.process_tasks_job.error_message)
        logservice.flush()
            
        self.process_tasks_job.job_progress_timestamp = datetime.datetime.now()
        self.process_tasks_job.put()
                
        self._log_progress("Error")
        
        shared.send_email_to_support("Worker - error msg to user", 
            self.process_tasks_job.error_message)



app = webapp2.WSGIApplication([ # pylint: disable=invalid-name
        (settings.WORKER_URL, ProcessTasksWorker),
    ], debug=True)  

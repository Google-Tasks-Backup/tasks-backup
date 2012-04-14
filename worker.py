import logging
import os
import pickle
import sys
#import urllib

from apiclient import discovery
from apiclient.oauth2client import appengine
from apiclient.oauth2client import client

from google.appengine.api import apiproxy_stub_map
from google.appengine.api import mail
from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp import util
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.runtime import apiproxy_errors
from google.appengine.runtime import DeadlineExceededError
from google.appengine.api import urlfetch_errors
from google.appengine.api import mail
from google.appengine.api.app_identity import get_application_id
from google.appengine.api import logservice # To flush logs

logservice.AUTOFLUSH_EVERY_SECONDS = 5
logservice.AUTOFLUSH_EVERY_BYTES = None
logservice.AUTOFLUSH_EVERY_LINES = 5
logservice.AUTOFLUSH_ENABLED = True

import httplib2

import model
import datetime
from datetime import timedelta
import time
import math

import settings
import appversion # appversion.version is set before the upload process to keep the version number consistent
import shared # Code whis is common between tasks-backup.py and worker.py


# Orig __author__ = "dwightguth@google.com (Dwight Guth)"
__author__ = "julie.smith.1999@gmail.com (Julie Smith)"




class CreateBackupWorker(webapp.RequestHandler):
    
    def post(self):
        fn_name = "CreateBackupWorker.post(): "
        
        start_time = datetime.datetime.now()
       
        logging.debug(fn_name + "<start> (app version %s)" %appversion.version)
        logservice.flush()

        client_id, client_secret, user_agent, app_title, project_name, host_msg = shared.GetSettings(self.request.host)
        
        
        user_email = self.request.get(settings.TASKS_QUEUE_KEY_NAME)
        
        is_test_user = shared.isTestUser(user_email)
        
        
        
        #logging.debug(fn_name + "User email = " + str(user_email))
        
        if user_email:
            
            # Retrieve the DB record for this user
            tasks_backup_job = model.TasksBackupJob.get_by_key_name(user_email)
            
            if tasks_backup_job is None:
                logging.error(fn_name + "No DB record for " + user_email)
                logservice.flush()
                # TODO: Find some way of notifying the user?????
            else:
                logging.info(fn_name + "Retrieved tasks backup job for " + str(user_email))
                logservice.flush()
                tasks_backup_job.status = 'building'
                tasks_backup_job.job_progress_timestamp = datetime.datetime.now()
                tasks_backup_job.put()
                
                user = tasks_backup_job.user
                if not user:
                    logging.error(fn_name + "No user object in DB record for " + str(user_email))
                    logservice.flush()
                    tasks_backup_job.status = 'error'
                    tasks_backup_job.error_message = "Problem with user details. Please restart."
                    tasks_backup_job.job_progress_timestamp = datetime.datetime.now()
                    tasks_backup_job.put()
                    self.response.set_status(401, "No user object")
                    return
                      
                credentials = tasks_backup_job.credentials
                if not credentials:
                    logging.error(fn_name + "No credentials in DB record for " + str(user_email))
                    logservice.flush()
                    tasks_backup_job.status = 'error'
                    tasks_backup_job.error_message = "Problem with user credentials. Please restart."
                    tasks_backup_job.job_progress_timestamp = datetime.datetime.now()
                    tasks_backup_job.put()
                    self.response.set_status(401, "No credentials")
                    return
              
                if credentials.invalid:
                    logging.error(fn_name + "Invalid credentials in DB record for " + str(user_email))
                    logservice.flush()
                    tasks_backup_job.status = 'error'
                    tasks_backup_job.error_message = "Invalid credentials. Please restart and re-authenticate."
                    tasks_backup_job.job_progress_timestamp = datetime.datetime.now()
                    tasks_backup_job.put()
                    self.response.set_status(401, "Invalid credentials")
                    return
              
                include_hidden = tasks_backup_job.include_hidden
                include_completed = tasks_backup_job.include_completed
                include_deleted = tasks_backup_job.include_deleted
                
                # User is authorised
                #logging.debug(fn_name + "Retrieved credentials from DB record")
                
                # Retrieve all tasks for the user
                try:

                    if is_test_user:
                        logging.debug(fn_name + "User is test user %s" % user_email)
                        logservice.flush()
                        
                    logging.info(fn_name + "include_hidden = " + str(include_hidden) +
                        ", include_completed = " + str(include_completed) +
                        ", include_deleted = " + str(include_deleted))
                    logservice.flush()
                    
                    #logging.debug(fn_name + "setting up http")
                    http = httplib2.Http()
                    http = credentials.authorize(http)
                    service = discovery.build("tasks", "v1", http)
                    
                    # Services to retrieve tasklists and tasks
                    #logging.debug(fn_name + "Setting up services to retrieve tasklists and tasks")
                    tasklists_svc = service.tasklists()
                    tasks_svc = service.tasks() 
                    
                    
                    
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
                        if is_test_user:
                            logging.debug(fn_name + "calling tasklists.list().execute() to create tasklists list")
                            logservice.flush()
                    
                        retry_count = 3
                        while retry_count > 0:
                          try:
                            if next_tasklists_page_token:
                               tasklists_data = tasklists_svc.list(pageToken=next_tasklists_page_token).execute()
                            else:
                               tasklists_data = tasklists_svc.list().execute()
                            # Successfully retrieved data, so break out of retry loop
                            break
                          except Exception, e:
                            retry_count = retry_count - 1
                            if retry_count > 0:
                                logging.warning(fn_name + "Error retrieving list of tasklists. " + 
                                    str(retry_count) + " retries remaining")
                                logservice.flush()
                            else:
                                logging.exception(fn_name + "Still error retrieving list of tasklists after retries. Giving up")
                                logservice.flush()
                                raise e
                    
                        if is_test_user and settings.DUMP_DATA:
                            logging.debug(fn_name + "tasklists_data ==>")
                            logging.debug(tasklists_data)
                            logservice.flush()

                        if tasklists_data.has_key(u'items'):
                          tasklists_list = tasklists_data[u'items']
                        else:
                          # If there are no tasklists, then there will be no 'items' element. This could happen if
                          # the user has deleted all their tasklists. Not sure if this is even possible, but
                          # checking anyway, since it is possible to have a tasklist without 'items' (see issue #9)
                          logging.warning(fn_name + "User has no tasklists.")
                          logservice.flush()
                          tasklists_list = []
                      
                        # tasklists_list is a list containing the details of the user's tasklists. 
                        # We are only interested in the title
                      
                        # if is_test_user and settings.DUMP_DATA:
                            # logging.debug(fn_name + "tasklists_list ==>")
                            # logging.debug(tasklists_list)


                        # ---------------------------------------
                        # Process all the tasklists for this user
                        # ---------------------------------------
                        for tasklist_data in tasklists_list:
                            total_num_tasklists = total_num_tasklists + 1
                          
                            if is_test_user and settings.DUMP_DATA:
                                logging.debug(fn_name + "tasklist_data ==>")
                                logging.debug(tasklist_data)
                                logservice.flush()
                          
                            """
                                Example of a tasklist entry;
                                    u'id': u'MDAxNTkzNzU0MzA0NTY0ODMyNjI6MDow',
                                    u'kind': u'tasks#taskList',
                                    u'selfLink': u'https://www.googleapis.com/tasks/v1/users/@me/lists/MDAxNTkzNzU0MzA0NTY0ODMyNjI6MDow',
                                    u'title': u'Default List',
                                    u'updated': u'2012-01-28T07:30:18.000Z'},
                            """ 
                       
                            tasklist_title = tasklist_data[u'title']
                            tasklist_id = tasklist_data[u'id']
                          
                            if is_test_user and settings.DUMP_DATA:
                                logging.debug(fn_name + "Process all the tasks in " + str(tasklist_title))
                                logservice.flush()
                                    
                            # Process all the tasks in this task list
                            tasklist_dict, num_tasks = self.GetTasksInTasklist(tasks_svc, tasklist_title, tasklist_id, is_test_user,
                                tasks_backup_job, include_hidden, include_completed, include_deleted)
                            # Track number of tasks per tasklist
                            tasks_per_list.append(num_tasks)
                            
                            total_num_tasks = total_num_tasks + num_tasks
                            tasks_backup_job.total_progress = total_num_tasks
                            tasks_backup_job.tasklist_progress = 0 # Because total_progress now includes num_tasks for current tasklist
                            tasks_backup_job.job_progress_timestamp = datetime.datetime.now()
                            tasks_backup_job.put()
                            
                            # if is_test_user:
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
                            # if is_test_user:
                                # logging.debug(fn_name + "There is (at least) one more page of tasklists to be retrieved")
                        else:
                            # This is the last (or only) page of results (list of tasklists)
                            more_tasklists_data_to_retrieve = False
                            next_tasklists_page_token = None
                          
                    # *** end while more_tasks_data_to_retrieve ***
                    
                    # These values are also sent by email at the end of this method
                    summary_msg = "Retrieved %d tasks from %d tasklists" % (total_num_tasks, total_num_tasklists)
                    breakdown_msg = "Tasks per list: " + str(tasks_per_list)
                    logging.info(fn_name + summary_msg + " - " + breakdown_msg)
                    logservice.flush()
                    
                    # ------------------------------------------------------
                    #   Store the data, so we can return it to the user
                    # ------------------------------------------------------
                      
 
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
                    
                    # Delete existing job records
                    tasklist_data_records = model.TasklistsData.gql("WHERE ANCESTOR IS :1",
                                                                db.Key.from_path(settings.DB_KEY_TASKS_DATA, user_email))

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
                    num_of_blobs = int(math.ceil(data_len * 1.0 / settings.MAX_BLOB_SIZE))
                    logging.debug(fn_name + "Calculated " + str(num_of_blobs) + " blobs required to store " + str(data_len) + " bytes")
                    logservice.flush()
                    
                    
                    
                    
                    try:
                        for i in range(num_of_blobs):
                            tasklist_rec = model.TasklistsData(db.Key.from_path(settings.DB_KEY_TASKS_DATA, user_email))
                            slice_start = int(i*settings.MAX_BLOB_SIZE)
                            slice_end = int((i+1)*settings.MAX_BLOB_SIZE)
                            # logging.debug(fn_name + "Creating part " + str(i+1) + " of " + str(num_of_blobs) + 
                                # " using slice " + str(slice_start) + " to " + str(slice_end))
                            
                            pkl_part = pickled_tasklists[slice_start : slice_end]
                            tasklist_rec.pickled_tasks_data = pkl_part
                            tasklist_rec.idx = i
                            tasklist_rec.put()
                            
                        # logging.debug(fn_name + "Marking backup job complete")
                        
                        # Mark backup completed
                        tasks_backup_job.status = 'completed'
                        tasks_backup_job.job_progress_timestamp = datetime.datetime.now()
                        tasks_backup_job.put()
                        logging.info(fn_name + "Marked job complete for " + str(user_email) + ", with progress = " + 
                            str(tasks_backup_job.total_progress))
                        logservice.flush()
                    except apiproxy_errors.RequestTooLargeError, e:
                        logging.exception(fn_name + "Error putting results in DB")
                        logservice.flush()
                        tasks_backup_job.status = 'error'
                        tasks_backup_job.error_message = "Tasklists data is too large - Unable to store tasklists in DB: " + str(e)
                        tasks_backup_job.job_progress_timestamp = datetime.datetime.now()
                        tasks_backup_job.put()
                    
                    except Exception, e:
                        logging.exception(fn_name + "Error putting results in DB")
                        logservice.flush()
                        tasks_backup_job.status = 'error'
                        tasks_backup_job.error_message = "Unable to store tasklists in DB: " + str(e)
                        tasks_backup_job.job_progress_timestamp = datetime.datetime.now()
                        tasks_backup_job.put()


                      
                      

                except urlfetch_errors.DeadlineExceededError, e:
                    logging.exception(fn_name + "urlfetch_errors.DeadlineExceededError:")
                    logservice.flush()
                    tasks_backup_job.status = 'error'
                    tasks_backup_job.error_message = "urlfetch_errors.DeadlineExceededError: " + str(e)
                    tasks_backup_job.job_progress_timestamp = datetime.datetime.now()
                    tasks_backup_job.put()
              
                except apiproxy_errors.DeadlineExceededError, e:
                    logging.exception(fn_name + "apiproxy_errors.DeadlineExceededError:")
                    logservice.flush()
                    tasks_backup_job.status = 'error'
                    tasks_backup_job.error_message = "apiproxy_errors.DeadlineExceededError: " + str(e)
                    tasks_backup_job.job_progress_timestamp = datetime.datetime.now()
                    tasks_backup_job.put()
                
                except DeadlineExceededError, e:
                    logging.exception(fn_name + "DeadlineExceededError:")
                    logservice.flush()
                    tasks_backup_job.status = 'error'
                    tasks_backup_job.error_message = "DeadlineExceededError: " + str(e)
                    tasks_backup_job.job_progress_timestamp = datetime.datetime.now()
                    tasks_backup_job.put()
                
                except Exception, e:
                    logging.exception(fn_name + "Exception:") 
                    logservice.flush()
                    tasks_backup_job.status = 'error'
                    tasks_backup_job.error_message = "Exception: " + str(e)
                    tasks_backup_job.job_progress_timestamp = datetime.datetime.now()
                    tasks_backup_job.put()
                
                end_time = datetime.datetime.now()
                process_time = end_time - start_time
                proc_time_str = "Processing time = " + str(process_time.seconds) + "." + str(process_time.microseconds) + " seconds"
                logging.info(fn_name + proc_time_str)
                logservice.flush()
                
                included_options_str = "Includes: Completed = %s, Deleted = %s, Hidden = %s" % (str(include_completed), str(include_deleted), str(include_hidden))
                try:
                    # sender = "stats@" + os.environ['APPLICATION_ID'] + ".appspotmail.com"
                    sender = "stats@" + get_application_id() + ".appspotmail.com"
                    subject = "[" + get_application_id() + "] " + summary_msg
                    #logging.info(fn_name + "Send stats email from " + sender)
                    mail.send_mail(sender=sender,
                        to="Julie.Smith.1999@gmail.com",
                        subject=subject,
                        body="Started: %s UTC\nFinished: %s UTC\n%s\n%s\n%s" % (str(start_time), str(end_time), proc_time_str, breakdown_msg, included_options_str ))
                except Exception, e:
                    logging.exception(fn_name + "Unable to send email")
                  

                
                # logging.info(fn_name + "Finished processing. Total progress = " + 
                    # str(tasks_backup_job.total_progress) + " for " + str(user_email))
        else:
            logging.error(fn_name + "No processing, as there was no user_email key")
            logservice.flush()
            
        logging.debug(fn_name + "<End>, user = " + str(user_email))
        logservice.flush()
    
    
    def GetTasksInTasklist(self, tasks_svc, tasklist_title, tasklist_id, is_test_user, tasks_backup_job, 
                           include_hidden, include_completed, include_deleted):
        """ Returns all the tasks in the tasklist 
        
            arguments:
              tasks_svc                -- reference to the common service used to retrieve tasks ( e.g., service.tasks() )
              tasklist_title           -- Name of the tasklist
              tasklist_id              -- ID used to retrieve tasks from this tasklist
                                          MUST match the ID returned in the tasklist data
              is_test_user             -- True if the user is a test user, to enable more detailed logging
              tasks_backup_job         -- DB entity for this backup job. Passed in so this method can updated timestamp and progress
              include_hidden           -- If true, include hidden tasks in the backup
              include_completed        -- If true, include completed tasks in the backup
              include_deleted          -- If true, include deleted tasks in the backup
              
            returns a tuple;
              two-element dictionary;
                'title' is a string, the name of the tasklist
                'tasks' is a list. Each element in the list is dictionary representing 1 task
              number of tasks
        """        
        fn_name = "CreateBackupHandler.GetTasksInTasklist(): "
        
        
        tasklist_dict = {} # Blank dictionary for this tasklist
        tasklist_dict[u'title'] = tasklist_title # Store the tasklist name in the dictionary
        
        num_tasks = 0

        more_tasks_data_to_retrieve = True
        next_tasks_page_token = None
        
        # Keep track of when last updated, to prevent excessive DB access which could exceed quota
        prev_progress_timestamp = datetime.datetime.now()
        
        if is_test_user and settings.DUMP_DATA:
          logging.debug(fn_name + "include_hidden = " + str(include_hidden) +
                            ", include_completed = " + str(include_completed) +
                            ", include_deleted = " + str(include_deleted))
          logservice.flush()
        # ---------------------------------------------------------------------------
        # Retrieve the tasks in this tasklist, and store as "tasks" in the dictionary
        # ---------------------------------------------------------------------------
        while more_tasks_data_to_retrieve:
        
          retry_count = 3
          while retry_count > 0:
            try:
              # Retrieve a page of (up to 100) tasks
              if next_tasks_page_token:
                # Get the next page of results
                # This happens if there are more than 100 tasks in the list
                # See http://code.google.com/apis/tasks/v1/using.html#api_params
                #     "Maximum allowable value: maxResults=100"
                tasks_data = tasks_svc.list(tasklist = tasklist_id, pageToken=next_tasks_page_token, 
                    showHidden=include_hidden, showCompleted=include_completed, showDeleted=include_deleted).execute()
              else:
                # Get the first (or only) page of results for this tasklist
                tasks_data = tasks_svc.list(tasklist = tasklist_id, 
                    showHidden=include_hidden, showCompleted=include_completed, showDeleted=include_deleted).execute()
              # Succeeded, so continue
              break
            except Exception, e:
              retry_count = retry_count - 1
              if retry_count > 0:
                logging.warning(fn_name + "Error retrieving tasks, " + 
                      str(retry_count) + " retries remaining")
                logservice.flush()
              else:
                logging.exception(fn_name + "Still error retrieving tasks for tasklist after retrying. Giving up")
                logservice.flush()
                raise e
              
          if is_test_user and settings.DUMP_DATA:
            logging.debug(fn_name + "tasks_data ==>")
            logging.debug(tasks_data)
          
          if not tasks_data.has_key(u'items'):
            # When using the Google Tasks webpage at https://mail.google.com/tasks/canvas, there will always
            # be at least one task in any tasklist, because when deleting the last task, a new blank task is
            # automatically created.
            # However, a third-party app (e.g., Calengoo on Android) CAN delete all the tasks in a task list,
            # which results in a tasklist without an 'items' element.
            logging.info(fn_name + "No tasks in tasklist")
            logservice.flush()
          else:
            try:
              tasks = tasks_data[u'items'] # Store all the tasks (List of Dict)
            except Exception, e:
              logging.exception(fn_name, "Exception extracting items from tasks_data. Dump follows ==>")
              logging.error(tasks_data)
              logservice.flush()
              raise e
            
            # if is_test_user and settings.DUMP_DATA:
              # logging.debug(fn_name + "tasks ==>")
              # logging.debug(tasks)
              # logservice.flush()
            
            # ------------------------------------------------------------------------------------------------
            # Fix date/time format for each task, so that the date/time values can be used in Django templates
            # Convert the yyyy-mm-ddThh:mm:ss.dddZ format to a datetime object, and store that
            # ------------------------------------------------------------------------------------------------
            for t in tasks:
              num_tasks = num_tasks + 1
              
              date_due = t.get(u'due')
              if date_due:
                t[u'due'] = datetime.datetime.strptime(date_due, "%Y-%m-%dT00:00:00.000Z").date()
                
              datetime_updated = t.get(u'updated')
              if datetime_updated:
                t[u'updated'] = datetime.datetime.strptime(datetime_updated, "%Y-%m-%dT%H:%M:%S.000Z")
              
              # There have been occassional format errors in the 'completed' property, 
              # due to 'completed' value such as "-1701567-04-26T07:12:55.000Z"
              # so if the format change fails, set 'completed' to None
              try:
                datetime_completed = t.get(u'completed')
                if datetime_completed:
                  new_datetime_completed = datetime.datetime.strptime(datetime_completed, "%Y-%m-%dT%H:%M:%S.000Z")
                  t[u'completed'] = new_datetime_completed
              except ValueError, e:
                  t[u'completed'] = datetime.datetime(datetime.MINYEAR, 1, 1, 0, 0, 0)
                  logging.exception(fn_name + "Invalid 'completed' timestamp format, so setting to 0001-01-01 00:00:00")
                  logging.debug(fn_name + "Invalid value was " + str(datetime_completed))
                  logservice.flush()
                
            if tasklist_dict.has_key(u'tasks'):
              # This is the n'th page of task data for this taslkist, so extend the existing list of tasks
              tasklist_dict[u'tasks'].extend(tasks)
            else:
              # This is the first (or only) list of task for this tasklist
              tasklist_dict[u'tasks'] = tasks
            
            # if is_test_user:
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
            # if is_test_user:
              # logging.debug(fn_name + "There is (at least) one more page of data to be retrieved")
              
            # More than one page, so update progress
            # Don't need to update here if no more pages, because calling method updates
            if (datetime.datetime.now() - prev_progress_timestamp).seconds > settings.TASK_COUNT_UPDATE_INTERVAL:
              tasks_backup_job.tasklist_progress = num_tasks
              tasks_backup_job.job_progress_timestamp = datetime.datetime.now()
              tasks_backup_job.put()
              prev_progress_timestamp = datetime.datetime.now()
          else:
            # This is the last (or only) page of results (list of tasks) for this task lists
            more_tasks_data_to_retrieve = False
            next_tasks_page_token = None
            
        if is_test_user:
          logging.debug(fn_name + "Retrieved " + str(num_tasks) + " tasks from " + tasklist_title)
        else:
          logging.debug(fn_name + "Retrieved " + str(num_tasks) + " tasks from task list")
        logservice.flush()  
        return tasklist_dict, num_tasks
        

def urlfetch_timeout_hook(service, call, request, response):
    if call != 'Fetch':
        return

    # Make the default deadline 30 seconds instead of 5.
    if not request.has_deadline():
        request.set_deadline(30.0)





def real_main():
    logging.debug("main(): Starting worker")
    
    apiproxy_stub_map.apiproxy.GetPreCallHooks().Append(
        'urlfetch_timeout_hook', urlfetch_timeout_hook, 'urlfetch')
    run_wsgi_app(webapp.WSGIApplication([
        ('/worker', CreateBackupWorker),
    ], debug=True))
    logging.debug("main(): <End>")

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
    
main = profile_main

if __name__ == '__main__':
    main()
    
    

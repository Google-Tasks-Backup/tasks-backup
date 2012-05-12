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

"""Classes to represent Tasks data"""

from apiclient.oauth2client import appengine

from google.appengine.ext import db
import datetime

import constants


class Credentials(db.Model):
  """Represents the credentials of a particular user."""
  credentials = appengine.CredentialsProperty(indexed=False)



class ProcessTasksJob(db.Model):
    """ Container used to pass User info (including credentials) to taskqueue task, and return tasks progress
        back to foreground process to be returned to the user.
    
        When creating an instance, the user's email address is used as the key
        
    """
    user = db.UserProperty(indexed=False)
    credentials = appengine.CredentialsProperty(indexed=False)
    
    # Used to include/exclude retrieved tasks which are completed and/or deleted and/or hidden
    include_completed = db.BooleanProperty(indexed=False, default=False)
    include_deleted = db.BooleanProperty(indexed=False, default=False)
    include_hidden = db.BooleanProperty(indexed=False, default=False)
    
    # Set automatically when entity is created. Indicates when job was started (i.e., snapshot time)
    # Also used to track if task exceeds maximum allowed, so we can display message to user
    job_start_timestamp = db.DateTimeProperty(auto_now_add=True, indexed=False)
    
    # Job status, to display to user and control web page and foreground app behaviour
    # status = db.StringProperty(indexed=False, choices=('starting', 'initialising', 'building', 'completed', 'importing', 'import_completed', 'error'), default='starting')
    status = db.StringProperty(indexed=False, choices=(constants.JobStatus.ALL_VALUES), default=constants.JobStatus.STARTING)
    
    # Total number of tasks backed up. Used to display progress to user. Updated when an entire tasklist has been backed up
    total_progress = db.IntegerProperty(indexed=False, default=0) 
    
    # Number of tasks in current tasklist. Used to display progress to user. Updated every 'n' seconds
    tasklist_progress = db.IntegerProperty(indexed=False, default=0) 
    
    # When job progress was last updated. Used to ensure that backup job hasn't stalled
    job_progress_timestamp = db.DateTimeProperty(auto_now_add=True, indexed=False) 
    
    error_message = db.StringProperty(indexed=False, default='')

    message = db.StringProperty(indexed=False, default='')


class TasklistsData(db.Model):
        pickled_tasks_data = db.BlobProperty(indexed=False) # NOTE: Blob max size is just under 1MB
        idx = db.IntegerProperty(default=0, indexed=True) # To reassemble in order        



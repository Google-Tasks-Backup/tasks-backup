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

# Extensively modified by Julie Smith 2012

"""Classes to represent Tasks data"""

from google.appengine.ext import db

from oauth2client import appengine

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
    
    # Used to include/exclude retrieved tasks which are completed and/or deleted and/or hidden
    include_completed = db.BooleanProperty(indexed=False, default=False)
    include_deleted = db.BooleanProperty(indexed=False, default=False)
    include_hidden = db.BooleanProperty(indexed=False, default=False)
    
    # Indicates when job was created (i.e., when /startbackup is called)
    job_created_timestamp = db.DateTimeProperty(auto_now_add=True, indexed=False)
    
    # Indicates when job was started by worker (i.e., snapshot time)
    # Also used to track if task exceeds maximum allowed, so we can display message to user
    job_start_timestamp = db.DateTimeProperty(indexed=False)
    
    # When job progress was last updated. Used to ensure that backup job hasn't stalled
    job_progress_timestamp = db.DateTimeProperty(auto_now_add=True, indexed=False) 
    
    # Job status, controls web page, worker and foreground app behaviour
    status = db.StringProperty(indexed=False, 
        choices=(constants.ExportJobStatus.ALL_VALUES),
        default=constants.ExportJobStatus.TO_BE_STARTED)
    
    # Total number of tasks backed up. Used to display progress to user. 
    # Updated when an entire tasklist has been backed up
    total_progress = db.IntegerProperty(indexed=False, default=0) 
    
    # Number of tasks in current tasklist. Used to display progress to user. Updated every 'n' seconds
    tasklist_progress = db.IntegerProperty(indexed=False, default=0) 
    
    # Error message from worker to user
    error_message = db.StringProperty(indexed=False, default='')

    # Message from worker to user, indicating what worker is doing
    message = db.StringProperty(indexed=False, default='')
    
    # Count of number of time this job has been started
    # This is used to prevent infinite loops of a job keeps dying
    number_of_job_starts = db.IntegerProperty(indexed=False, default=0) 

    # The RSA public key is used to encrypt the AES key
    public_key_b64 = db.StringProperty(indexed=False, default='')
    
    # The AES key is encrypted using the RSA public key
    # The decrypted AES key is used to decrypt the encrypted tasklist data
    encrypted_aes_key_b64 = db.StringProperty(indexed=False, default='')
    

class TasklistsData(db.Model):
    """ The user's tasklists are pickled, encrypted and stored in 1 or more blobs """
    pickled_tasks_data = db.BlobProperty(indexed=False) # NOTE: Blob max size is just under 1MB
    idx = db.IntegerProperty(default=0, indexed=True) # To reassemble in order        


    
class UsageStats(db.Model):
    """ Used to track GTB usage.
    
        user_hash and start_time together form a unique key
        
        In order for the stats to be useful, all 9 properties must be set.
    """
    
    # ID is used so that total number of retrievals, retrievals per user, and number of users can be determined 
    # To provide a measure of privacy, use hash to uniquely identify user, rather than the user's actual email address
    # Note that there is a very small probability that multiple users may be hashed to the same value
    user_hash  = db.IntegerProperty(indexed=True)
    
    # Time that data retrieval was started
    start_time = db.DateTimeProperty(indexed=True)
    
    number_of_tasks = db.IntegerProperty(indexed=False)
    
    number_of_tasklists = db.IntegerProperty(indexed=False)
    
    # Each element in the list indicates the number of tasks in each tasklist 
    tasks_per_tasklist = db.ListProperty(int, indexed=False)
    
    # User's data retrieval choices
    include_completed = db.BooleanProperty(indexed=False)
    include_deleted = db.BooleanProperty(indexed=False)
    include_hidden = db.BooleanProperty(indexed=False)
    
    # The number of seconds taken to retrieve the tasks
    processing_time = db.FloatProperty(indexed=False)
    
    
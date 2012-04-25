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
    
    # A job can either be export (backup) or import
    job_type = db.StringProperty(indexed=False, choices=('import', 'export'), default='export')
    
    # Blobstore key for import job. The key is retrievable in the uploadhandler (i.e., when user uploads file)
    #       class UploadHandler(blobstore_handlers.BlobstoreUploadHandler):
    #           def post(self):
    #               upload_files = self.get_uploads('file') # Assuming form uses <input type="file" name="file">
    #               blobstore_info = upload_files[0]
    #               blobstore_key = blobstore_info.key
    # CAUTION: The Blobstore is global across the app. The only way to tie a Blobstore to a user is through this Model!
    blobstore_key = db.StringProperty(indexed=False, default=None)
    
    # Used to include/exclude retrieved tasks which are completed and/or deleted and/or hidden
    include_completed = db.BooleanProperty(indexed=False, default=False)
    include_deleted = db.BooleanProperty(indexed=False, default=False)
    include_hidden = db.BooleanProperty(indexed=False, default=False)
    
    # Set automatically when entity is created. Indicates when job was started (i.e., snapshot time)
    # Also used to track if task exceeds maximum allowed, so we can display message to user
    job_start_timestamp = db.DateTimeProperty(auto_now_add=True, indexed=False)
    
    # Job status, to display to user and control web page and foreground app behaviour
    status = db.StringProperty(indexed=False, choices=('starting', 'building', 'completed', 'importing', 'import_completed', 'error'), default='starting')
    
    # Total number of tasks backed up. Used to display progress to user. Updated when an entire tasklist has been backed up
    total_progress = db.IntegerProperty(indexed=False, default=0) 
    
    # Number of tasks in current tasklist. Used to display progress to user. Updated every 'n' seconds
    tasklist_progress = db.IntegerProperty(indexed=False, default=0) 
    
    # When job progress was last updated. Used to ensure that backup job hasn't stalled
    job_progress_timestamp = db.DateTimeProperty(auto_now_add=True, indexed=False) 
    
    error_message = db.StringProperty(indexed=False, default=None)

    # message = db.StringProperty(indexed=False, default=None)


class TasklistsData(db.Model):
        pickled_tasks_data = db.BlobProperty(indexed=False) # NOTE: Blob max size is just under 1MB
        idx = db.IntegerProperty(default=0, indexed=True) # To reassemble in order        



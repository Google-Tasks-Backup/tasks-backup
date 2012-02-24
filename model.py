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
  credentials = appengine.CredentialsProperty()


class TasksBackupJob(db.Model):
    """ Container used to pass User info (including credentials) to taskqueue task, and return tasks progress
        back to foreground process to be returned to the user.
    
        When creating an instance, the user's email address is used as the key
        
    """
    user = db.UserProperty(indexed=False)
    credentials = appengine.CredentialsProperty(indexed=False)
    
    # Set status default="building" and progress default=0
    
    timestamp = db.DateTimeProperty(auto_now_add=True, indexed=False)
    status = db.StringProperty(choices=("starting", "building", "completed", "error"), default="starting")
    progress = db.IntegerProperty(indexed=False, default=0) # Number of tasks backed up. Used to display progress to user
    error_message = db.StringProperty(indexed=False, default=None)

class TasklistsData(db.Model):
        pickled_tasks_data = db.BlobProperty(indexed=False)
        idx = db.IntegerProperty(default=0, indexed=True) # To reassemble in order        





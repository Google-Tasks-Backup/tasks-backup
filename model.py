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
    
    # Used to include/exclude tasks which are completed and/or deleted and/or hidden
    include_completed = db.BooleanProperty(indexed=False, default=False)
    include_deleted = db.BooleanProperty(indexed=False, default=False)
    include_hidden = db.BooleanProperty(indexed=False, default=False)
    
    # Set automatically when entity is created. Indicates when job was started (i.e., snapshot time)
    # Also used to track if task exceeds maximum allowed, so we can display message to user
    job_start_timestamp = db.DateTimeProperty(auto_now_add=True, indexed=False)
    
    # Job status, to display to user and control web page and foreground app behaviour
    status = db.StringProperty(choices=("starting", "building", "completed", "error"), default="starting")
    
    # Total number of tasks backed up. Used to display progress to user. Updated when an entire tasklist has been backed up
    total_progress = db.IntegerProperty(indexed=False, default=0) 
    
    # Number of tasks in current tasklist. Used to display progress to user. Updated every 'n' seconds
    tasklist_progress = db.IntegerProperty(indexed=False, default=0) 
    
    # When job progress was last updated. Used to ensure that backup job hasn't stalled
    job_progress_timestamp = db.DateTimeProperty(auto_now_add=True, indexed=False) 
    
    error_message = db.StringProperty(indexed=False, default=None)

class TasklistsData(db.Model):
        pickled_tasks_data = db.BlobProperty(indexed=False)
        idx = db.IntegerProperty(default=0, indexed=True) # To reassemble in order        


class Task():
    """ Representation of a task to be used by the recurse tag in customjango """
    
    # Property descriptions from 
    # https://developers.google.com/google-apps/tasks/v1/reference/tasks#resource

    # string	Task identifier.
    id = None
    
    # string	Title of the task.
    title = None
    
    # string	Status of the task. This is either "needsAction" or "completed".
    status = None
    
    # OPTIONAL: datetime	Due date of the task (as a RFC 3339 timestamp).
    due = None
    
    # datetime	Last modification time of the task (as a RFC 3339 timestamp).
    updated = None 
    
    # string	String indicating the position of the task among its sibling tasks
    # under the same parent task or at the top level. 
    # If this string is greater than another task's corresponding position string 
    # according to lexicographical ordering, the task is positioned after the other
    # task under the same parent task (or at the top level). 
    # This field is read-only. Use the "move" method to move the task to another position.
    position = None
    
    # OPTIONAL: datetime	Completion date of the task (as a RFC 3339 timestamp). 
    # This field is omitted if the task has not been completed.
    completed = None
    
    # OPTIONAL:string	Notes describing the task. 
    notes = None  
    
    # OPTIONAL: boolean	Flag indicating if task has been deleted. Default False.
    deleted = None 
    
    # OPTIONAL: boolean	Flag indicating whether the task is hidden. 
    # This is the case if the task had been marked completed when the task list was last cleared. 
    # The default is False. This field is read-only.
    hidden = False
    
    # OPTIONAL	string	Parent task identifier. (id of the parent of this task)
    # This field is omitted if it is a top-level task. This field is read-only. 
    # Use the "move" method to move the task under a different parent or to the top level.
    parent = None 
    
    # OPTIONAL: list	Collection of links. This collection is read-only.	
    #       links[].type	    string	Type of the link, e.g. "email".	
    #       links[].description	string	The description. In HTML speak: Everything between <a> and </a>.	
    #       links[].link	    string	The URL.
    links = None
	
    # ============ Additional properties required by customjango.py recurse tag ===============
    parent_ = None # returns None if the item is a root item
    children = [] # List of children of this task
    
    
    # ============= Other properties, not used by tasks-backup ==================
    # kind	                string	Type of the resource. This is always "tasks#task".
    # etag	                etag	ETag of the resource.
    # selfLink	            string	URL pointing to this task. Used to retrieve, update, or delete this task.
    # links[]	            list	Collection of links. This collection is read-only.	
    # links[].type	        string	Type of the link, e.g. "email".	
    # links[].description	string	The description. In HTML speak: Everything between <a> and </a>.	
    # links[].link	        string	The URL.    
    

    def __init__(self, task):
        """ Initialise Task from a task dictionary """
        
        self.id = task.get(u'id', None)
        self.title = task.get(u'title', None)
        self.notes = task.get(u'notes', None)
        self.status = task.get(u'status', None)
        self.due = task.get(u'due', None)
        self.completed = task.get(u'completed', None)
        self.updated = task.get(u'updated', None)
        self.deleted = task.get(u'deleted', None)
        self.hidden = task.get(u'hidden', None)
        self.parent = task.get(u'parent', None)
        self.position = task.get(u'position', None)
#        self.parent = task.get(u'parent_', None)
        self.children = task.get(u'children', [])
        self.links = task.get(u'links', None)
        self.parent_ = task.get(u'parent', None) # returns None if the item is a root item


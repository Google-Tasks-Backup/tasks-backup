#!/usr/bin/python2.5
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

# This module contains any value, especially strings, that is referenced in more than one location.

class ExportJobStatus(object):
    # CAUTION: The Django progress.html template uses string literals when checking the status value. 
    # If these values are changed, then the progress.html must also be changed
    STARTING = 'Starting' # Job has been created (request places on task queue)
    INITIALISING = 'Initialising' # Pre-job initialisation (e.g., retrieving credentials)
    BUILDING = 'Building' # Building list of tasks (for export or display)
    EXPORT_COMPLETED = 'Export completed'
    ERROR = 'Error'
    
    ALL_VALUES = [STARTING, INITIALISING, BUILDING, EXPORT_COMPLETED, ERROR]
    PROGRESS_VALUES = [STARTING, INITIALISING, BUILDING]
    STOPPED_VALUES = [EXPORT_COMPLETED, ERROR]

    
# Max blob size is just under 1MB (~2^20), so use 1000000 to allow some margin for overheads
MAX_BLOB_SIZE = 1000000

# Number of times to retry server actions
# Exceptions are usually due to DeadlineExceededError on individual API calls
NUM_API_RETRIES = 3

# Name of folder containg templates. Do not include path separator characters, as they are inserted by os.path.join()
PATH_TO_TEMPLATES = "templates"

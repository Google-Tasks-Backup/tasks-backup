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

class ExportJobStatus(object): # pylint: disable=too-few-public-methods
    # CAUTION: The Django progress.html template uses string literals when checking the status value. 
    # If these values are changed, then the progress.html must also be changed
    TO_BE_STARTED = 'Starting' # Job has been created (request places on task queue)
    INITIALISING = 'Initialising' # Pre-job initialisation (e.g., retrieving credentials)
    BUILDING = 'Building' # Building list of tasks (for export or display)
    EXPORT_COMPLETED = 'Export completed'
    ERROR = 'Error'
    
    ALL_VALUES = [TO_BE_STARTED, INITIALISING, BUILDING, EXPORT_COMPLETED, ERROR]
    PROGRESS_VALUES = [TO_BE_STARTED, INITIALISING, BUILDING]
    STOPPED_VALUES = [EXPORT_COMPLETED, ERROR]

    
# Max blob size is just under 1MB (~2^20), so use 1000000 to allow some margin for overheads
MAX_BLOB_SIZE = 1000000

# Name of folder containg templates. Do not include path separator characters, as they are inserted by os.path.join()
PATH_TO_TEMPLATES = "templates"

RSA_PRIVATE_KEY_COOKIE_NAME = 'private_key_b64'


# Sometimes the 'completed' timestamp is '0000-01-01T00:00:00.000Z', which cannot be converted
# to a datetime object.
ZERO_RFC3339_DATETIME_STRING = '0000-01-01T00:00:00.000Z'

# This is how we display ZERO_RFC3339_DATETIME_STRING to the user for datetime fields such as 'completed'
ZERO_DATETIME_STRING = '0000-01-01 00:00:00'

# This is how we display ZERO_RFC3339_DATETIME_STRING to the user for date-only fields such as 'due'
ZERO_DATE_STRING = '0000-01-01'

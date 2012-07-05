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

# Portions based on Dwight Guth's Google Tasks Porter

# Rename this file as settings.py and set the client ID and secrets values 
# according to the values from https://code.google.com/apis/console/

# Client ID and Secret values from the "API Access" page at https://code.google.com/apis/console/

# Client IDs, secrets, user-agents and host-messages are indexed by host name, 
# to allow the application to be run on different hosts, (e.g., test and production),
# without having to change these values each time.

# URL's starting with a number are the n'th version on the server. 
# The version number is specified in app.yaml
# This allows a way to test a different non-default version before making it default.

client_ids = { 'tasks-backup.appspot.com'                  : '998877665544.apps.googleusercontent.com',
               'www.tasks-backup.appspot.com'              : '998877665544.apps.googleusercontent.com',
               'my-test-server.appspot.com'                : '112233445566.apps.googleusercontent.com',
               'localhost:8087'                            : '123456123456.apps.googleusercontent.com'}
                
client_secrets = { 'tasks-backup.appspot.com'              : 'MyClientSecret',
                   'www.tasks-backup.appspot.com'          : 'MyClientSecret',
                   'my-test-server.appspot.com'            : 'MyClientSecret',
                   'localhost:8087'                        : 'MyClientSecret'}

user_agents = { 'tasks-backup.appspot.com'                 : 'tasks-backup/0.7',
                'www.tasks-backup.appspot.com'             : 'tasks-backup/0.7',
                'my-test-server.appspot.com'               : 'tasks-backup-test/0.7',
                'localhost:8087'                           : 'tasks-backup-q-local/0.7'}
# User agent value used if no entry found for specified host                
DEFAULT_USER_AGENT = 'tasks-backup/0.7'


# This value is displayed as the title of all web pages, and within app pages (e.g., as a self-reference to the app)
app_titles = {'my-test-server.appspot.com'                 : "Google Tasks Backup - Test", 
              'localhost:8087'                             : "Google Tasks Backup (Local 8087)",
              'tasks-backup.appspot.com'                   : "Google Tasks Backup",
              'www.tasks-backup.appspot.com'               : "Google Tasks Backup"}
# Title used when host name is not found
DEFAULT_APP_TITLE = "Google Tasks Backup"


# According to the "Application Settings" admin page 
#   (e.g., https://appengine.google.com/settings?app_id=s~js-tasks&version_id=4.356816042992321979)
# "Application Title:" is "Displayed if users authenticate to use your application."
# However, the valiue that is shown under "Authorised Access" appears to be the value 
# set on the "API Access" page

# This is the value displayed under "Authorised Access to your Google Account"
# at https://www.google.com/accounts/IssuedAuthSubTokens
# The product name is set in the API Access page as "Product Name", at
# https://code.google.com/apis/console and is linked to the client ID
product_names = { '998877665544.apps.googleusercontent.com'    : "Google Tasks Backup", 
                  '112233445566.apps.googleusercontent.com'    : "JS Tasks",
                  '425175418944.apps.googleusercontent.com'    : "JS Tasks Test",
                  '123456123456.apps.googleusercontent.com'    : "GTB Local"}
# Product name used if no matching client ID found in product_names 
DEFAULT_PRODUCT_NAME = "Google Tasks Backup"

# Host messages are optional. If set, it is displayed as a heading at the top of web pages
host_msgs = { 'my-test-server.appspot.com'                 : "Running on test server", 
              'localhost:8087'                             : "*** GTB on local host port 8087 ***",
              'tasks-backup.appspot.com'                   : "Google Tasks Backup - Beta",
              'www.tasks-backup.appspot.com'               : "Google Tasks Backup - Beta"}

url_discussion_group = "groups.google.com/group/tasks-backup"

email_discussion_group = "tasks-backup@googlegroups.com"

url_issues_page = "code.google.com/p/tasks-backup/issues/list"

url_source_code = "code.google.com/p/tasks-backup/source/browse/"

# Must match name in queue.yaml
PROCESS_TASKS_REQUEST_QUEUE_NAME = 'process-tasks-request'

# The string used used with the params dictionary argument to the taskqueue, 
# used as the key to retrieve the value from the task queue
TASKS_QUEUE_KEY_NAME = 'user_email'

WELCOME_PAGE_URL = '/'

MAIN_PAGE_URL = '/main'

START_BACKUP_URL = '/startbackup'

PROGRESS_URL = '/progress'

RESULTS_URL = '/results'

INVALID_CREDENTIALS_URL = '/invalidcredentials'

WORKER_URL = '/worker'

DB_KEY_TASKS_BACKUP_DATA = 'tasks_backup_data'

# Maximum number of consecutive authorisation requests
# Redirect user to Invalid Credentials page if there are more than this number of tries
MAX_NUM_AUTH_RETRIES = 3

# Number of times to try server actions
# Exceptions are usually due to DeadlineExceededError on individual API calls
# The first (NUM_API_TRIES - 2) retries are immediate. The app sleeps for 
# WORKER_API_RETRY_SLEEP_DURATION or FRONTEND_API_RETRY_SLEEP_DURATION seconds 
# before trying the 2nd last and last retries.
NUM_API_TRIES = 4

# Number of seconds for worker to sleep for the last 2 API retries
WORKER_API_RETRY_SLEEP_DURATION = 45


# Number of seconds for frontend to sleep for the last API retries
# The total amount of time allowed for a page response is 60 seconds. 
# An API call times out after 5 seconds, so 4 API tries is up to 20 seconds
# The API_RETRY_SLEEP_DURATION should be less than 
# (60 - (NUM_API_TRIES - 2) * 5 - (2 * (5 + FRONTEND_API_RETRY_SLEEP_DURATION)))
# i.e., if NUM_API_TRIES = 4, FRONTEND_API_RETRY_SLEEP_DURATION should be LESS than 20 sec
FRONTEND_API_RETRY_SLEEP_DURATION = 18



# Maximum number of seconds allowed between the start of a job, and when we give up.
# i.e., display error message and stop refreshing progress.html
# Should be at least 600 seconds (10 minutes), as that is the maximum amount of time that a taskqueue task can run
MAX_JOB_TIME =  665

# If the user has more than this number of tasks, display a warning message that
# displaying as an HTML page may fail
LARGE_LIST_HTML_WARNING_LIMIT = 10000

# If the job hasn't been updated in MAX_JOB_PROGRESS_INTERVAL seconds, assume that the job has stalled, 
# and display error message and stop refreshing progress.html
# Longest observed time between job added to taskqueue, and worker starting, is 94.5 seconds
MAX_JOB_PROGRESS_INTERVAL = 125

# Update number of tasks in tasklist every TASK_COUNT_UPDATE_INTERVAL seconds
# This prevents excessive Datastore Write Operations which can exceed quota
TASK_COUNT_UPDATE_INTERVAL = 5

# Refresh progress page every PROGRESS_PAGE_REFRESH_INTERVAL seconds
PROGRESS_PAGE_REFRESH_INTERVAL = 6

# Number of pixels for each depth level for sub-tasks
# e.g., for a 3rd level subtask, indent would be 3 * TASK_INDENT
TASK_INDENT = 40


# Maximum number of consecutive authorisation requests
# Redirect user to Invalid Credentials page if there are more than this number of tries
MAX_NUM_AUTH_REQUESTS = 4

# Auth count cookie expires after 'n' seconds. 
# That is, we count the number of authorisation attempts within 'n' seconds, and then we reset the count back to zero.
# This prevents the total number of authorisations over a user session being counted (and hence max exceeded) if the user has a vey long session
AUTH_RETRY_COUNT_COOKIE_EXPIRATION_TIME = 60

# ###############################################
#                  Debug settings
# ###############################################

# Extra detailed and/or personal details may be logged when user is one of the test accounts
# If accessing a limited access server (below), only test accounts will be granted access
TEST_ACCOUNTS = ["Test1@gmail.com", "Test2@gmail.com", "Test3@gmail.com"]


# When the app is running on one of these servers, users will be rejected unless they are in TEST_ACCOUNTS list
# If there is/are no limited-access servers, set this to an empty list []
LIMITED_ACCESS_SERVERS = ['my-test-server.appspot.com']
#LIMITED_ACCESS_SERVERS = []

# Display log menu option on the Progress page if user is in SPECIAL_USERS
SHOW_LOG_OPTION_USERS = ["Test.User@gmail.com", "another.user@gmail.com"]

# Logs dumps of raw data for test users when True
DUMP_DATA = False



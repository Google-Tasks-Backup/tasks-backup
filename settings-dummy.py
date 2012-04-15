# Rename this file as settings.py and set the client ID and secrets values 
# according to the values from https://code.google.com/apis/console/

# Client IDs, secrets, user-agents and host-messages are indexed by host name, 
# to allow the application to be run on different hosts, (e.g., test and production),
# without having to change these values each time.

client_ids = { 'tasks-backup.appspot.com'                  : '123456789012.apps.googleusercontent.com',
               'tb-test-server.appspot.com'                : '987654321987.apps.googleusercontent.com',
               'localhost:8084'                            : '999999999999.apps.googleusercontent.com'}
                
client_secrets = { 'tasks-backup.appspot.com'              : 'MyVerySecretKeyForProdSvr',
                   'tb-test-server.appspot.com'            : 'MyVerySecretKeyForTestSvr',
                   'localhost:8084'                        : 'MyVerySecretKeyForLocalSvr'}
                
user_agents = { 'tasks-backup.appspot.com'                 : 'tasks-backup/1.0',
                'tb-test-server.appspot.com'               : 'tasks-backup-test/1.0',
                'localhost:8084'                           : 'tasks-backup-local/1.0'}

# User agent value used if no entry found for specified host                
DEFAULT_USER_AGENT = 'tasks-backup/2.0'

# This should match the "Application Title:" value set in "Application Settings" in the App Engine
# administration for the server that the app will be running on. This value is displyed in the app,
# but the value from the admin screen is "Displayed if users authenticate to use your application."
app_titles = {'tb-test-server.appspot.com'                 : "Test - Google Tasks Backup", 
              'localhost:8084'                             : "Local - Google Tasks Backup",
              'tasks-backup.appspot.com'                   : "Google Tasks Backup" }
                
# Title used when host name is not found, or not yet known
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
product_names = { '164364198675.apps.googleusercontent.com'    : "Google Tasks Backup", 
                  '823249731479.apps.googleusercontent.com'    : "JS Tasks",
                  '425175418944.apps.googleusercontent.com'    : "JS Tasks Test",
                  '314627146721.apps.googleusercontent.com'    : "GTB Local"}

# Product name used if no matching client ID found in product_names 
DEFAULT_PRODUCT_NAME = "Google Tasks Backup"

# Host messages are optional
host_msgs = { 'tb-test-server.appspot.com'                 : "*** Running on test AppEngine server ***", 
              'localhost:8084'                             : "*** Running on local host ***",
              'tasks-backup.appspot.com'                   : "Beta" }

url_discussion_group = "groups.google.com/group/tasks-backup"

email_discussion_group = "tasks-backup@googlegroups.com"

url_issues_page = "code.google.com/p/tasks-backup/issues/list"

url_source_code = "code.google.com/p/tasks-backup/source/browse/"

# Must match name in queue.yaml
BACKUP_REQUEST_QUEUE_NAME = 'tasks-backup-request'

TASKS_QUEUE_KEY_NAME = 'user_email'

HOME_PAGE_URL = '/'

START_BACKUP_URL = '/startbackup'

PROGRESS_URL = '/progress'

RESULTS_URL = '/results'

INVALID_CREDENTIALS_URL = '/invalidcredentials'

DB_KEY_TASKS_DATA = 'tasks_data'

# Max blob size is just under 1MB (~2^20), so use 1000000 to allow some margin for overheads
MAX_BLOB_SIZE = 1000000

# Maximum number of seconds allowed between the start of a job, and when we give up.
# i.e., display error message and stop refreshing progress.html
MAX_JOB_TIME =  650

# If the user has more than this number of tasks, display a warning message that
# displaying as an HTML page may fail
LARGE_LIST_HTML_WARNING_LIMIT = 6000

# If the job hasn't been updated in MAX_JOB_PROGRESS_INTERVAL seconds, assume that the job has stalled, 
# and display error message and stop refreshing progress.html
MAX_JOB_PROGRESS_INTERVAL = 90

# Update number of tasks in tasklist every TASK_COUNT_UPDATE_INTERVAL seconds
# This prevents excessive Datastore Write Operations which can exceed quota
TASK_COUNT_UPDATE_INTERVAL = 5

# Refresh progress page every PROGRESS_PAGE_REFRESH_INTERVAL seconds
PROGRESS_PAGE_REFRESH_INTERVAL = 8

# Number of pixels for each depth level for sub-tasks
# e.g., for a 3rd level subtask, indent would be 3 * TASK_INDENT
TASK_INDENT = 40


# Maximum number of consecutive authorisation requests
# Redirect user to Invalid Credentials page if there are more than this number of tries
MAX_NUM_AUTH_REQUESTS = 4

# ###############################################
#                  Debug settings
# ###############################################

# Extra detailed and/or personal details may be logged when user is one of the test accounts
TEST_ACCOUNTS = ["My.Email.Address@gmail.com", "Test.Email.Address@gmail.com"]


# When the app is running on one of these servers, users will be rejected unless they are in TEST_ACCOUNTS list
# If there is/are no limited-access servers, set this to an empty list []
LIMITED_ACCESS_SERVERS = []
#LIMITED_ACCESS_SERVERS = ['my-test-server.appspot.com']

# Logs dumps of raw data for test users when True
DUMP_DATA = False


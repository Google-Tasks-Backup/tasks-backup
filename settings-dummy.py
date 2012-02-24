# Client ID and Secret values from https://code.google.com/apis/console/

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

# Title used when host name is not found, or not yet known
DEFAULT_APP_TITLE = "Google Tasks Backup"

# This should match the "Application Title:" value set in "Application Settings" in the App Engine
# administration for the server that the app will be running on. This value is displyed in the app,
# but the value from the admin screen is "Displayed if users authenticate to use your application."
app_titles = {'tb-test-server.appspot.com'                 : "Test - Google Tasks Backup", 
              'localhost:8084'                             : "Local - Google Tasks Backup",
              'tasks-backup.appspot.com'                   : "Google Tasks Backup" }
                
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

START_BACKUP_URL = '/startbackup'

PROGRESS_URL = '/progress'

RESULTS_URL = '/results'

DB_KEY_TASKS_DATA = 'tasks_data'

# Max blob size is just under 1MB (~2^20), so use 1000000 to allow some margin for overheads
MAX_BLOB_SIZE = 1000000

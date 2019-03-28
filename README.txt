
3 Nov 2012, Julie Smith
-----------------------

This project is based on google-tasks-porter by dwightguth@google.com
It appears that google-tasks-porter stalled in the latter part of 2011. In
2012, Julie Smith modified google-tasks-porter to create Google Tasks Backup,
which is now running at
    tasks-backup.appspot.com
    
There is a discussion group at groups.google.com/group/tasks-backup
and issues list at code.google.com/p/tasks-backup/issues/list


In order to run Google Tasks Backup under your own account, you will need to;
  - Edit the values for 'version' and 'application' in apps.yaml
  - Copy settings-dummy.py to settings.py and modify values as described in that file
  - Copy host_settings-dummy.py to host_settings.py and modify values as described in that file
  - Change the Google Analytics ID in /templates/inc_google_analytics.html {line 4}
    If you do not wish to use Google Analytics, delete everything in that file
  

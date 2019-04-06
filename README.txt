Google Tasks Backup is used to allow a user to back up their Google Tasks 
in a variety of formats.

========================

This project is based on google-tasks-porter by dwightguth@google.com
It appears that google-tasks-porter stalled in the latter part of 2011. In
2012, Julie Smith created Google Tasks Backup (GTB), partly based on some of
the original concepts and source code of google-tasks-porter.

GTB is now running at
  tasks-backup.appspot.com
  
There is also an associated Google Tasks Importer (GTI) running at
  import-tasks.appspot.com
    
There is a discussion group at groups.google.com/group/tasks-backup


17 Jun 2015, Julie Smith
------------------------

If you wish to fork GTB and run it under your own appspot.com account, you will
need to create/modify the following files with your own values;

  Copy settings-dummy.py to settings.py and change (at least) the following values;
    url_discussion_group
    email_discussion_group
    url_issues_page    
    url_source_code
    TEST_ACCOUNTS
    PRODUCTION_SERVERS
    
  Copy host_settings-dummy.py to host_settings.py and follow the instructions
    in that file for obtaining and inserting your own client ID and secret values.

  Copy app-dummy.yaml to app.yaml and set values for 'version' and 'application'
  
  Set the 'version' and 'upload_timestamp' values in appversion.py
    This is the version information that is displayed to the user on every webpage.
    
  Change the Google Analytics ID in /templates/inc_google_analytics.html {line 4}
    If you do not wish to use Google Analytics, delete everything in that file
  
27 Mar 2018, Julie Smith
------------------------
v0.14 fixed an issue where subtasks were not being exported


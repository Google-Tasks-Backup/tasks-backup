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

  Set values for 'version' and 'application' in app.yaml
  
  Set the 'version' and 'upload_timestamp' values in appversion.py
    This is the version information that is displayed to the user on every webpage.
    


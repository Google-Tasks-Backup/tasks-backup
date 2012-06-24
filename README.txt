
2 Feb 2012, Julie Smith
-----------------------
In order to run Google Tasks Backup under your own account, you will need to 
modify apps.yaml, and set the client ID and secrets values in the settings.py 
file. There is a sample settings-dummy.py file which contains all the required 
settings, with instructions on getting and inserting your own client ID and 
secret values.

There is a discussion group at groups.google.com/group/tasks-backup
and issues list at code.google.com/p/tasks-backup/issues/list

This project is based on google-tasks-porter by dwightguth@google.com
It appears that google-tasks-porter stalled in the latter part of 2011. In
2012, Julie Smith modified google-tasks-porter to create Google Tasks Backup,
running at
    tasks-backup.appspot.com
    
= = = = = = =

Original Google Tasks Porter README, as at 22 Jan 2012

This project requires a module in the root directory named "settings" which
defines the values of CLIENT_ID and CLIENT_SECRET on the module level as
strings representing the OAuth credentials of the program requesting access.
The CLIENT_ID variable should not include the suffix of
".apps.googleusercontent.com".

If you have any questions about the code please contact
google-tasks-porter@googlegroups.com.

Remember: this project requires Google App Engine to run.  If you want to
host your own copy on App Engine you will need to modify the application ID in
app.yaml and then use your App Engine SDK to upload it.

Note: The oauth2client package was moved into the apiclient directory in order
to fix the weird pickle error. See
http://groups.google.com/group/google-appengine/browse_thread/thread/3d56681cb27b18cc/8ca673403a784680

google-api-python-client retrieved from: http://code.google.com/p/google-api-python-client/
on: June 7, 2011
version: 1.0beta2
consisting of: apiclient, httplib2, oauth2client, uritemplate

vobject retrieved from: http://vobject.skyhouseconsulting.com/history.html
on: August 11, 2011
version: 0.8.1c
consisting of: vobject

dateutil retrieved from: http://labix.org/python-dateutil
on: August 11, 2011
version: 1.5
consisting of: dateutil

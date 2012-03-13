2012-03-14 06-13
version = 'beta 0.5.049'
Testing on js-tasks
Only uses html1 template for "Julie.Smith.1999@gmail.com"
Correctly indents tasks using the html1 template
- Couldn't get Django recurse to work
- Relies on each task's 'depth' property, which is calculated and 
  added to each task dictionary object in ReturnResultsHandler.post()



2012-03-08 10:08
version = 'beta 0.5.025'
Live on tasks-backup (version 5)
Added enhancements as per issues #7 and #10
Separated export from display
Added user options for HTML tasks display formatting
Improved layout of HTML tasks display


2012-03-07 14:11
Version beta 0.5.010
Tested on 6.js-tasks
Dims hidden and deleted tasks, and optionally dims completed tasks, in HTML view
Escape title and notes in HTML view, so that text is not potentially interpretted as HTML.



24 Feb 2012
Version beta 0.4.034
Worker queue successfully processed over 22,000 tasks for a single user, and frontend successfully returned results to user.


23 Feb 2012, 03:26
------------------
Version beta 0.4.034
Worker queue successfully processed 5321 tasks, and frontend successfully returned results to user.

=================================================================



21 Feb 2012, 08:40
Put a while loop around try/except around tasklists_svc.list() and tasks_svc.list() to allow 3 retries

21 Feb 2012 07:36
Tested on js-tasks.appspot.com
Works as long as the tasks kist is not too large.
- 601 tasks in 6 lists works, 
- 5000+ tasks fails because it is too large for the datastore
Still getting occassional urlfetch_errors.DeadlineExceededError exceptions, despite having copied code from GTP
to extend timout to 30 seconds.


21 Feb 2012, 03:40
This version uses a taskqueue task to process the retrieval of tasks.
Sort-of works running on localhost, however;
- Continual errors;
    ERROR    2012-02-20 16:18:45,515 taskqueue_stub.py:1857] An error occured while sending the task "task1" (Url: "/worker") in queue "tasks-backup-request". Treating as a task error.
    Traceback (most recent call last):
      File "C:\Program Files\Google\google_appengine\google\appengine\api\taskqueue\taskqueue_stub.py", line 1849, in ExecuteTask
        response = connection.getresponse()
      File "C:\Programs\Python\lib\httplib.py", line 1027, in getresponse
        response.begin()
      File "C:\Programs\Python\lib\httplib.py", line 407, in begin
        version, status, reason = self._read_status()
      File "C:\Programs\Python\lib\httplib.py", line 365, in _read_status
        line = self.fp.readline()
      File "C:\Programs\Python\lib\socket.py", line 430, in readline
        data = recv(1)
    timeout: timed out
    WARNING  2012-02-20 16:18:45,515 taskqueue_stub.py:1937] Task task1 failed to execute. This task will retry in 131.072 seconds

- CreateBackupWorker.post() is being called multiple times.
- progress page is not showing progress, even when backup has been completed
-- If I manually stop and start dev server, and then go to progress page, the results can be returned to user
- progress value in DB is always 0
- Task retry_parameters are ignored. 
-- Set for task_retry_limit: 3 & task_age_limit: 15s, but log shows "This task will retry in 131.072 seconds"
-- At least 17 retries


-------------
19 Feb 2012
Version beta 0.3.058 works as long as the tasks retrieval takes less than 60 seconds, as Google throws a DeadlineExceeded error if the time is exceeded.
Long-term solution is to move processing to a separate task using taskqueue (as google-tasks-porter did).
I am trying to find an alternative to the DB method that is used by GTP, as using DB exceeded my Datastore Write Operations quota for anything more than a few hundred tasks.


2 Feb 2012, Julie Smith
-----------------------
This project is based on google-tasks-porter by dwightguth@google.com

It appears that google-tasks-porter stalled in the latter part of 2011.

In 2012, Julie Smith modified google-tasks-porter to create tasks-backup,
a simplified task exporter which does not use db.Model, as that was causing 
the quota to be exceeded.

= = = = = = =

Original README, as at 22 Jan 2012

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

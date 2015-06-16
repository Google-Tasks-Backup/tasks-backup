**Google Tasks Backup** allows a user to back up their Google Tasks in one of several formats;

  * **Microsoft Outlook** (.csv file)
  * **iCalendar** (.ics file)
  * **Python** (.py file with tasklists as a data structure )
  * **Remember The Milk** (email) `   ` _{untested}_
  * **Raw Dump** (.csv file), contains all 15 Google Tasks fields
  * **Text file** (.txt file), with tasks indented using either spaces or tabs
  * **Import/Export CSV** (.csv file) used to import tasks using http://import-tasks.appspot.com
  * **Import/Export GTBak** (custom GTBak format) used to import tasks using http://import-tasks.appspot.com
    * This format has better support for international and extended characters, and is recommended for backup and restore operations.

**Google Tasks Backup** can also display tasks as a single web page (e.g., suitable for printing).


_Other formats such as **hTodo** (HTML page) may be added if sufficient people request it at http://code.google.com/p/tasks-backup/issues/list_

This App Engine application is written in Python, and uses Google's API to access the user's Google Tasks.

The application is currently running at http://tasks-backup.appspot.com/


---

This project was created to continue the good work done by Dwight at http://code.google.com/p/google-tasks-porter/
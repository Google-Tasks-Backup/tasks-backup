<a href='Hidden comment: 
This page shows revisions that affect the user. For full source code revision notes, refer to the commit log messages at http://code.google.com/p/tasks-backup/source/list or use hg.
'></a>

## Google Tasks Backup version history ##


---


#### 0.9.064 (2013-05-04 04:39) ####

New features;
  * Option to adjust timezone to use local time for 'updated' and 'completed' fields in export file and/or on display page.
    * The export and display forms each have their own timezone selectors. This allows, for example, files to be exported using the default UTC whilst displaying tasks uses the chosen timezone
    * The Google Tasks server uses its own clock, which runs at UTC (aka GMT) when tasks are marked complete. Up until now, GTB exported the date/time exactly as it was stored by the server. This means that sometimes a task marked completed would appear to have been completed on the next or previous day (depending on how far west or east the user is from London). This new option allows the user to apply a correction so that the times exported or displayed by GTB should be the same as the local time of the user. This addresses [issue #17](https://code.google.com/p/tasks-backup/issues/detail?id=#17) but has some limitations as listed on the AdjustingForTimezones page
  * Saves all user selections on main and results pages (so long as cookies are enabled)

Bug fix;
  * Fix issue where due date selection would occasionally go to 0001-01-01


---


#### 0.9.035 (2013-04-22 16:31) ####

Added "Raw CSV, RFC3339 timestamps" export format, which exports 'due', 'completed' and 'updated' timestamps in the original RFC-3399 format used by the Google Tasks server. The file also includes those fields in a human-readable format.


---



#### 0.9.026 (2013-03-31 16:14) ####

Updated code to use Python 2.7 (due to Google deprecating Python 2.5 on GAE)


---


#### 0.8.159 (2013-03-10 17:10) ####

New feature;
  * Added option to export tasks as a text file. Tasks can be exported as either a tabbed-text or spaced-text format.


---


#### 2012-11-26 21:59, beta 0.8.121 ####

Minor bug fixes;
  * Fix issue where 1st retry on API error in worker caused a 45 second sleep
  * Fixed issues URL link on web pages


---



#### 2012-11-03 13:44, beta 0.8.106 ####
Bug fixes;
  * [Issue 14](https://code.google.com/p/tasks-backup/issues/detail?id=14), [Issue 15](https://code.google.com/p/tasks-backup/issues/detail?id=15); Changed authentication handling to reduce "Authentication failed" errors
  * Improved server timeout handling

Other;
  * Improve handling of dates before 1900
  * Added special handling of '0001-01-01 00:00:00' completed date
  * Updated icon
  * Many minor code and usability tweaks. Refer to 'Changes since last commit.txt' in the source


---


#### 2012-07-05 20:00, beta 0.7.311 ####

Bug fix;
  * `NameError: global name 'time' is not defined`


---


#### 2012-07-01 19:56, beta 0.7.303 ####

Bug fix;

  * [Issue 15](https://code.google.com/p/tasks-backup/issues/detail?id=15); Improved handling of authentication failure


---


#### 2012-06-29 00:10, beta 0.7.274 ####

  * Added Print button to tasks display page.
  * Added backup job timestamp to progress page, to indicate that the backup was taken at a particular time.
  * Improved message for possible server error when authenticating.


---


#### 2012-06-27 02:13, beta 0.7.265 ####
Bug fixes;

  * [Issue 16](https://code.google.com/p/tasks-backup/issues/detail?id=16); Now displays appropriate message to user if a backup does not yet exist for that user (instead of `"UnboundLocalError: local variable 'include_completed' referenced before assignment"`)

Other;
  * Noted that date/time fields in the Import/Export CSV file must be prefixed with "UTC " before being imported using [Import Tasks](http://import-tasks.appspot.com) (if user edits the CSV file before import)


---


#### 2012-06-24 16:02, beta 0.7.256 ####
Bug fixes;

  * Fixed error when displaying empty tasklist.
  * Now displays today's date (or previously selected date) in the due date filter. Was displaying 0001-01-01 if user didn't include completed tasks.
  * Fixed broken links in main & user format selection (progress) pages to notes 4 & 5 on info page.
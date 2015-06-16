#### Issues when adjusting for difference between user's local time and Google Tasks server time ####

The Google Tasks server runs at UTC (aka GMT), so when a user completes a task, the server records it as being completed at the corresponding UTC time (Note 1).

Up until 4 May 2013, GTB returned the date/time stored by the server. This sometimes resulted in the exported 'completed' date appearing to be out by one day (Note 2).

GTB now has a timezone selection option, which allows the user to select their offset from UTC. GTB adds the user's chosen offset to the server time to calculate the local time. Note that _this will not always provide the correct date/time (Notes 3 & 4)_, but should work in most instances.




The biggest impact of the difference between local time and UTC is that a task exported by GTB may appear to have been completed on the previous or next day when imported into another application (e.g. Outlook).

> For example;
    * If a user in New York (UTC-5) marks a task complete after 7:00 pm, the task will appear to have been completed on the next day, because the Google Tasks server ticks over past midnight UTC at 7:00pm New York time.
    * If a user in Sydney (UTC+10) marks a task complete before 10:00 am, the task will appear to have been completed on the previous day, because the Google Tasks server doesn't tick over past midnight until 10:00 am Sydney time.


#### A partial solution ####

The timezone selection option provides a partial solution, as it allows GTB to add or subtract the specified number of hours from times stored on the Google Tasks server. This will not solve all time offset issues.

> For example;
    * If you were in a different timezone when you completed a task, neither the server nor GTB knows that, so there is no way to report the local time that the task was completed (Note 3).
    * GTB cannot compensate for daylight savings time. This means that if a task is completed during daylight savings time, and the export is run during standard time, there will be a one-hour window where tasks may still be reported as being completed on the next or previous day (Note 4).


#### Summary ####
So, in summary, selecting using the timezone offset should reduce the number of tasks which appear to have been completed on the previous or next day, but will not entirely eliminate the issue.



```





```


---


#### NOTES ####

**Note 1**
The Google Tasks server does not necessarily know the user's local time, so it has no choice but to use UTC.



**Note 2**
For example, if a New York user marks a task complete at any time after 7:00 pm, it will appear to have been completed the next day, because the server ticks over past midnight at 7:00 pm New York time (UTC - 5).

The difference between the user's time and UTC depends on the user's timezone (i.e. how far east or west the user is from London). For people west of London, the Google server times appears in the future, whereas the server times appear in the past for those east of London.



**Note 3**
A user who travels makes reporting completed times using local time impossible.

For example, a user who lives in New York (UTC-5) may travel to Los Angeles (UTC-8) and mark a task complete there at 10:00 pm. There is no way for either the server or GTB to know that the user was in LA when the task was completed, so GTB is unable to return the local time of where the task was completed. So, when the user runs GTB with the New York timezone (UTC-5), GTB will return the time in New York when the task was completed (i.e. 1:00 am the next day).



**Note 4**
Another complication is daylight savings time. For example, if a task is completed in standard time, but the GTB export is run in daylight-savings time, the conversions would be out by one hour for any task completed in standard time. It is not feasible to try to correct for daylight savings time, because each country (and even each state in some countries) has different start/end times for daylight savings time.
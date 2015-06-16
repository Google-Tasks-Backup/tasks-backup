<h1>Common GTB usage scenarios</h1>



## Using GTB and GTI to copy tasks between two different Google accounts ##

One of the most common scenarios is to backup from one account using GTB and then import the tasks into a different account using GTI.

  1. Sign into `account1`
  1. Start [GTB](https://tasks-backup.appspot.com/) and authorise as required
  1. From the Main Menu, select which tasks to include;
    * _For a full backup, check all 3 options. If all you want is to export your incomplete tasks, uncheck all 3 options.
      * Include completed tasks
      * Include deleted tasks
      * Include hidden tasks
    * Click the question-mark icon after each option for more details on each option._
  1. Click the **`[Retrieve Tasks]`** button to start the backup.
  1. GTB will show the progress of the backup. How long this takes depends on the number of tasks being exported.
  1. When all tasks have been retrieved from the Google Tasks server, GTB displays a menu allowing you to choose the format of the export file.
  1. Create a backup file by choosing the **"Import/Export GTBak"** option and then click the **`[Export Tasks Data]`** button.
  1. Save this .GTBak file to your computer.
    * The default name of the file is automatically set by GTB as     `tasks_gtb_MYEMAILADDRESS@gmail.com_YYYY-MM-DD.GTBak` where `YYYY-MM-DD` is the date on the server (which is UTC, so may differ from your local date).
  1. Sign out of `account1`
  1. Sign into `account2`
  1. Start [GTI](https://import-tasks.appspot.com/) and authorise as required
  1. From the Main Menu, choose the **"Create new tasklists"** option.
    * _Other options may be more appropriate, depending on the reason for the import.
      * For example, if restoring a backup to the same account, it may be more appropriate to choose "Delete all tasklists before import".
      * For example, if importing from multiple accounts, the "Append own suffix" may be useful.
    * Click the question-mark icon after each option for more details on each option._
  1. Click on the **`[Choose File]`** button.
  1. Select the .GTBak file saved in step 8.
  1. GTI will start the import process and display the progress. How long this takes depends on the number of tasks being imported.
    * Note that importing can take up to 10 times longer than exporting, as the Google Tasks server is very slow at creating new tasks.
  1. If the import is taking a long time (because many tasks are being imported), you can close the GTI web page, as the import will continue in the background.
    * You will receive an email (sent to `account2`) when the import is complete.
    * If you have not received an email within 24 hours, go to https://import-tasks.appspot.com/progress to check the progress.


---


## Using GTI to restore tasks from a previous GTB backup ##

GTI can restore an earlier backup to the same account (e.g. because your tasks have been accidentally deleted or corrupted by an external app):

  1. Start [GTI](https://import-tasks.appspot.com/) and authorise as required
  1. From the Main Menu, choose the **"Delete all tasklists before import"** option.
  1. Click on the **`[Choose File]`** button.
  1. Select a .GTBak file from a previously saved GTB session.
  1. GTI will start the import process and display the progress. How long this takes depends on the number of tasks being imported.
    * Note that importing can take up to 10 times longer than exporting, as the Google Tasks server is very slow at creating new tasks.
  1. If the import is taking a long time (because many tasks are being imported), you can close the GTI web page, as the import will continue in the background.
    * You will receive an email (sent to to the currently logged in account) when the import is complete.
    * If you have not received an email within 24 hours, go to https://import-tasks.appspot.com/progress to check the progress.


---


## Notes ##

  1. Due to a limitation of the Google Tasks Server, the default tasklist cannot be deleted, so if there are any tasks in the default tasklist, they will still be there after importing using GTI.
  1. GTI may rename the default tasklist if it clashes with the name of an imported tasklist, depending on which import method was chosen.
{% comment %}
This is used to return a Python-compatible dump of the user's tasks.

    Example structure;
    
    tasklists = 
        [
            {
                u'title': u'Test list',
                u'tasks':
                    [
                        {
                            u'status': u'completed', 
                            u'kind': u'tasks#task', 
                            u'parent': u'IdStringOfParent', 
                            u'title': u'Task title ', 
                            u'deleted': True, 
                            u'completed': datetime.datetime(2012, 3, 5, 12, 15, 10), 
                            u'updated': datetime.datetime(2012, 3, 5, 12, 15, 12), 
                            u'due': datetime.date(2012, 3, 2), 
                            u'etag': u'"eTagString"', 
                            u'id': u'UniqueTaskIdString', 
                            u'position': u'00000000000000004482', 
                            u'notes': u"Some notes\nMore notes on 2nd line", 
                            u'links': 
                                [
                                    {
                                        u'type': u'email', 
                                        u'link': u'https://mail.google.com/mail/#all/EmailMsgIdString', 
                                        u'description': u'Email Subject String'
                                    }
                                ],
                            u'selfLink': u'https://www.googleapis.com/tasks/v1/lists/UniqueTasklistIdString/tasks/UniqueTaskIdString'
                        }, 
                        # More tasks
                    ]
            },
            {
                u'title': u'Another list',
                u'tasks':
                    [
                        {
                            # Task elements
                        }
                    ]
            },
            # More tasklists
        ]
    

"autoescape off" is used to prevent ' (single quote) being converted to &#39;

{% endcomment %}{% autoescape off %}
import datetime

tasklists = {{ tasklists }}
{% endautoescape %}

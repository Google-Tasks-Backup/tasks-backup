{% comment %}
Copyright 2012 Julie Smith.  All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.


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

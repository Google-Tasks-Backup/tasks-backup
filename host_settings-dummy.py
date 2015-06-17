# Rename this file as host_settings.py and change the values as required.
# The client ID and secrets values are obtained from 'API Access' at https://code.google.com/apis/console/
#   1. Click the "API Access" under the [API Project] button
#   2. Click on [Create an OAuth 2.0 client ID...]   {or [Create another client ID...] if an ID has been created previously}
#   3. If prompted, fill in the branding information (minimum is Product Name) and click [Next]
#   4. Ensure that "Application type" is set to "Web application"
#   5. Enter the URL for your application (i.e. my-app-id.appspot.com)
#      If testing on local dev server, enter "http://localhost:10080/oauth2callback"
#   6. Click [Create client ID]
#   7. Copy the values from "Client ID:" and "Client secret:" to CLIENT_ID and CLIENT_SECRET

CLIENT_ID = '998877665544.apps.googleusercontent.com'
CLIENT_SECRET = 'MyClientSecret'
SCOPE = 'https://www.googleapis.com/auth/tasks'
USER_AGENT = 'my-product/1.0' # My product name and version
APP_TITLE = 'My application name' # Whatever you want
PRODUCT_NAME = 'My product name' # (as per 'API Access' at https://code.google.com/apis/console/)
HOST_MSG = '*** Beta ***' # Whatever you want

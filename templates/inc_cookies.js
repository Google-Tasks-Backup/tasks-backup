
            function setCookie(name,value,days) {
                // From http://www.quirksmode.org/js/cookies.html
                // If days = 0, the cookie is deleted when the user closes the browser. 
                // If days < 0, the cookie is deleted immediately.
                if (days) {
                    var date = new Date();
                    date.setTime(date.getTime()+(days*24*60*60*1000));
                    var expires = "; expires="+date.toGMTString();
                }
                else var expires = "";
                document.cookie = name+"="+escape(value)+expires+"; path=/";
            }

            function getCookie(name) {
                // From http://www.quirksmode.org/js/cookies.html
                var nameEQ = name + "=";
                var ca = document.cookie.split(';');
                for(var i=0;i < ca.length;i++) {
                    var c = ca[i];
                    while (c.charAt(0)==' ') c = c.substring(1,c.length);
                    if (c.indexOf(nameEQ) == 0) return unescape(c.substring(nameEQ.length,c.length));
                }
                return null;
            }

            function eraseCookie(name) {
                // From http://www.quirksmode.org/js/cookies.html
                setCookie(name,"",-1);
            }        
        
            function boolToStr(b) {
                if (b) {
                    return 'true';
                } else {
                    return 'false';
                }
            }
            
            function strToBool(s) {
                if (s && s.toLowerCase() == 'true') {
                    return true;
                } else {
                    return false;
                }
            }
            

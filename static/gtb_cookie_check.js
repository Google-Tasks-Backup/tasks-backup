/**
 * Display elements based on whether user has cookies enabled or not. 
 *
 * If cookies are enabled, elements with the "display-if-cookies-enabled" class will be displayed
 * otherwise elements with the "display-if-cookies-disabled" class will be displayed.
 *
 * Requires the following 2 CSS classes;
 *
 *    .display-if-cookies-enabled {
 *        display:none;
 *        margin: 0;
 *    }
 *    
 *    .display-if-cookies-disabled {
 *        display:none;
 *        margin: 0;
 *    }
 *
 * Usage:
 *    window.addEventListener('DOMContentLoaded', (event) => {
 *       checkIfCookiesAreEnabled();
 *    });
 */
function checkIfCookiesAreEnabled() {
    let fn_name = "checkIfCookiesAreEnabled(): "
    
    console.log(fn_name + "Checking if cookies are enabled");
    let className;
    try {
        if (navigator.cookieEnabled) {
            // Unhide any elements with 'display-if-cookies-enabled' class
            className = "display-if-cookies-enabled";
            console.log(fn_name + "Cookies are enabled");
            // Display the authorise/main-menu button
        } else {
            // Unhide any elements with 'display-if-cookies-disabled' class
            className = "display-if-cookies-disabled";
            console.log(fn_name + "WARNING: Cookies are disabled");
            // Display the "Cookies required" message
        }                    
    }
    catch (error) {
        className = "display-if-cookies-disabled";
        console.error(fn_name + "WARNING: Unable to determine if cookies are enabled: " +
            error);
    }
    
    let elements = document.getElementsByClassName(className);
    if (elements) {
        console.log(fn_name + "Displaying " + elements.length + " elements with '" +
            className + "' class");
        for (let i=0; i < elements.length; i++) {
            elements[i].style.display = 'block';
        }
    } else {
        console.log(fn_name + "No elements found with '" + className + "' class");
    }
}

window.addEventListener('DOMContentLoaded', (event) => {
    checkIfCookiesAreEnabled();
});

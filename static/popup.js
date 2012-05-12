/***************************/
//@Author: Adrian "yEnS" Mato Gondelle
//@website: www.yensdesign.com
//@email: yensamg@gmail.com
//@license: Feel free to use it, but keep this credits please!	
// 2012-04-27, modified by Julie Smith
/***************************/

/* To use, add the following elements to the webpage:
 * ==================================================
 * 1. For each element which is to trigger a popup, set class="popupTrigger" and id="XXXXX", e.g.,
 *          <img class="popupTrigger" id="displayHelp1" src="/static/help.png" alt="Display help">
 *    Multiple elements may have the same ID, and all those elements will trigger the same popup.
 * 2. Create a div with the content to be displayed in the popup, and set class="popup" and id="XXXXX-content",
 *    where XXXXX is the ID used in step 1. e.g.,
 *          <div class="popup" id="displayHelp1-content">Some content</div>
 *    Note that the content div is not allowed in certain elements (such as <legend>). In that case,
 *    place the content div just after that element.
 *    The pop will display in the position where the content div appears within the source. 
 *    e.g., if the content div is the last element in the body, the popup will appear at the bottom of the page.
 * 5. Add an empty div with class="backgroundPopup" to the bottom of the page
 *          <div class="backgroundPopup"></div>
 * 6. To enable a close button in the popup, add an element within the content div specified in step 2, 
 *    with class="popupClose", e.g.
 *          <a class="popupClose">X</a>
 *      OR
 *          <img class="popupClose" src="close.png" alt="Close">
 * 7. The element after the the popupClose imag should have class="clear", so that the close button is above the rest of the content.
 */

// Keep track of current popup state
//0 means disabled; 1 means enabled;
var popupStatus = 0;

// Id of the currently displayed popup
var currentPopupId = "";

function setDimensions() {
    if(popupStatus==1) {
        // If popup is to be displayed, sets size of popup and background
        $(currentPopupId).width($(window).width()/3.3);
        var popupWidth = $(currentPopupId).width();
        var windowWidth = $(window).width();
        $(currentPopupId).css({
            "left": windowWidth/2-popupWidth/2
        });
        /* 
         * NOTE: On IE9, height:100% and width:100% in CSS only creates a background as big as the visible window, 
         * minus padding/borders. We set the height and width here to ensure that the background fully covers
         * the document. This is especially important if user scrolls, and then tries to click outside the popup to close the popup.
         * IE9 also ignores opacity, so that is also set here using the fadeTo() method.
         */
        // Need to set height here for IE9, because 100% in CSS uses viewport height.
        // Need to add some extra height, because otherwise IE9 still leaves a small gap at the bottom of the page.
        $(".backgroundPopup").height($(document).outerHeight(true)+20);
        // User outerWidth, because IE excludes margins when setting inner element to 100%
        $(".backgroundPopup").width($("body").outerWidth(true));
    }
}

//loading popup with jQuery magic!
function loadPopup(){
	//loads popup only if it is disabled
	if(popupStatus==0){
		popupStatus = 1;
        setDimensions();
		$(currentPopupId).css({
			"opacity": "0.95"
		});
        $(".backgroundPopup").fadeTo("fast", 0.4);
		$(currentPopupId).fadeIn("fast");
	}
}

//disabling popup with jQuery magic!
function disablePopup(){
	//disables popup only if it is enabled
	if(popupStatus==1){
		$(".backgroundPopup").fadeOut("fast");
		$(currentPopupId).fadeOut("fast");
		popupStatus = 0;
	}
}



function grabID(e){ 
    // Return the ID of the element that triggered the event. Used so we know which popup to display.
    // From http://www.dynamicdrive.com/forums/archive/index.php/t-8167.html
    //   "modified from script at: http://www.quirksmode.org/js/events_properties.html#target"
    try 
    {
        var targ;
        if (!e) var e = window.event;
        if (e.target) targ = e.target;
        else if (e.srcElement) targ = e.srcElement;
        if (targ.nodeType == 3) // defeat Safari bug
        targ = targ.parentNode;
        return targ.id;
    }
    catch (err)
    {
        return '';
    }
}

//CONTROLLING EVENTS IN jQuery
$(document).ready(function(){
    
    // Try to catch any resize event, so that the popup width can be set,
    // and backgound size adjusted to fill the whole page again.
    // Note that no event is fired in IE9 if user zooms (i.e., Ctrl+Mousewheel or Ctrl+'+')!
    $(window).resize(function(){
        setDimensions();
    });

    // Display popup when user clicks on any "popupTrigger" class element
    $(".popupTrigger").click(function(e){
            // Display popup when user clicks on any "popupTrigger" class element
            //currentPopupId = "#" + event.target.id + "-content";
            currentPopupId = "#" + grabID(e) + "-content";
            loadPopup();
        });
        
        
    //Close current popup when user clicks on any "popupClose" class element (usually 'X' text or image)
    $(".popupClose").click(function(){
        disablePopup();
    });
    
    //Close current popup when user clicks on the popup background
    $(".backgroundPopup").click(function(){
        disablePopup();
    });
    
    //Close current popup when user presses Escape, Enter or Space
    $(document).keyup(function(e){
        if(popupStatus==1){
            if (e.keyCode==27 || e.keyCode==13 || e.keyCode==32) 
            {
                disablePopup();
            }
        }
    });
});
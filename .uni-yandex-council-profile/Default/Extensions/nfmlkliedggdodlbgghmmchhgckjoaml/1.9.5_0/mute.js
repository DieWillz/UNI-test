/*
try {
    throw new Error("StopExecution");
} catch (e) {
    if (e.message === "StopExecution") {
        // Stop further execution
    } else {
        throw e; // Rethrow other errors
    }
}
*/


/*
if (typeof window.onlyonetimebugfix === 'undefined') 
{
    window.onlyonetimebugfix = 0; //initialize, just once
}
*/



console.log("mute");

chrome.storage.local.get(['staticrules'], (result0) => {
    chrome.storage.local.get(['exceptions'], (result) => {

    //if (enabledRulesets.includes("ruleset_1") || enabledRulesets.includes("ruleset_2")) 
    if(result0.staticrules != "disabled")
    {
      console.log(`enabled.`); //partial or complete adblocking enabled -> use css based adblocking as well!
      //check if manually disabled;
      var hostname = window.location.hostname;
      
        if(result.exceptions == null || result.exceptions == undefined || result.exceptions == "" || result.exceptions.length == 0)
        {
          //exceptions list empty: blocking enabled on all websites
          if(document.readyState === 'complete')
          {
              //setTimeout(bugfixes, 1300);
              onload();
          }
          else
          {
          document.addEventListener('readystatechange', function(e) 
          {
           if(document.readyState === 'complete') 
           {
                // The document is fully loaded.
                //setTimeout(bugfixes, 1300);
                onload();
           }
           return;
          });
          }
        }
        else if(hostname && result.exceptions.includes(hostname))
        {
            //included in list of exceptions: ad blocking disabled, don't trigger ad muting as well
            return;
        }
        else
        {
            //not there in the list of exceptions -> adblocking enabled
            if(document.readyState === 'complete')
            {
                //setTimeout(bugfixes, 1300);
                onload();
            }
            else
            {
            document.addEventListener('readystatechange', function(e) 
            {
             if(document.readyState === 'complete') 
             {
                  // The document is fully loaded.
                  //setTimeout(bugfixes, 1300);
                  onload();
             }
             return;
            });
            }            
        }  
    } 
    else 
    {
      //=== disabled for sure
      console.log(`disabled.`); //adblocking disabled totally -> dont do spotify muting
    }
}); 
}); 

/*
chrome.storage.local.get(['exceptions'], (result) => {
	if(result.exceptions == null || result.exceptions == undefined || result.exceptions == "")
	{
	  chrome.storage.local.set({ 'exceptions': [] });
	  //not there in exceptions, bcz empty array, blocking enabled
	  //enabled => continue
	}
	else if(result.exceptions.includes(window.location.hostname))
	{
		//included in exceptions: blocking disabled
		return;
	}
	else
	{
		//not there in the list, blocking enabled
		//enabled => continue
	}

if(document.readyState === 'complete')
{
    setTimeout(bugfixes, 1300);
    onload();
}
else
{
document.addEventListener('readystatechange', function(e) 
{
 if(document.readyState === 'complete') 
 {
      // The document is fully loaded.
      setTimeout(bugfixes, 1300);
      onload();
 }
 return;
});
}

});
*/

/*
function bugfixes()
{

//bug fix
var element = document.querySelector('[aria-label="error-dialog.generic.header"]');
var element2 = document.querySelector('[aria-label="Something went wrong"]');

if(element || element2) 
{
    var strmsg = 
    `Blockify can't work properly if there are other Spotify ad-blockers running. Please turn off other Spotify ad-blockers (except Blockify) and reload the page.`;
    alert(strmsg);

    console.log(window.onlyonetimebugfix);
    //either of these elements
    if(element && element.querySelector('[data-encore-id="buttonPrimary"]') && window.onlyonetimebugfix === 0)
    {
        //if element exists and btn inside element and not clicked yet
        //click on button side that element, update flag
        window.onlyonetimebugfix = 1; 
        element.querySelector('[data-encore-id="buttonPrimary"]').click();
        console.log("Spotify bug fixed!"); //should auto-reload once
        if(window.event)
        {
        window.event.stopImmediatePropagation();
        window.event.stopPropagation();
        window.event.preventDefault();
        }
    }
    else if(element2 && element2.querySelector('[data-encore-id="buttonPrimary"]') && window.onlyonetimebugfix === 0)
    {
        window.onlyonetimebugfix = 1;  
        element2.querySelector('[data-encore-id="buttonPrimary"]').click();
        console.log("Spotify bug fixed!"); //should auto-reload once
        if(window.event)
        {
        window.event.stopImmediatePropagation();
        window.event.stopPropagation();
        window.event.preventDefault();
        }
    }
    else if(window.onlyonetimebugfix === 1)
    {
        //should be reloading now
        //should ignore 2nd click, w8
    }
    else
    {
        //window.location.reload();
        //button not found or something
        //can be risky, do not hide

        if(document.getElementById("bugfix_for_spotify"))
        {
          document.getElementById("bugfix_for_spotify").remove();
        } //can't see elements - something else - let the user tackle it

        console.log("Spotify bug found!");
    }
} 
else 
{  
  //all good
  console.log("All good!");
  if(document.getElementById("bugfix_for_spotify"))
  {
    document.getElementById("bugfix_for_spotify").remove();
  } //remove css hider
}
};
*/

/*
function hidetoast() 
{
    var snackbar = document.getElementById("snackbar");
    if(snackbar)
    {
        snackbar.className = snackbar.className.replace("show", ""); 
    }
};
*/
/*
function showToast3(text)
{
    var snackbar = document.getElementById("snackbar");
    if(snackbar)
    {
    snackbar.innerText = text;
    snackbar.className = "show";
    }
}
*/

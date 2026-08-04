//checkPermissions();
console.log("4");

function checkPermissions() 
{
    console.log("5");
    chrome.permissions.contains({
      origins: ["*://*/*"]
    }, function(result) 
    {
      if (result) 
      {
        // Permission is already granted
        // Do something here, e.g., execute code that requires the permission
       // registerScriptIfNeeded2();
      } 
      else 
      {
        // Permission is not granted, prompt the user
        //req();
       // window.parent.postMessage('REQ now!!', '*');
      }
    });
};

// function registerScriptIfNeeded2() {
   // var contentScript = {
   //     id: 'contentSCR',
  //      matches: ["*://*/*"],
/*        js: ['css.js'],
        persistAcrossSessions: true,
        runAt: 'document_idle'
    };
    
    chrome.scripting.getRegisteredContentScripts((scripts) => {
        console.log("Currently registered scripts:", scripts); // Log all registered scripts for debugging
        // Check if the script with given ID is already registered
        var isAlreadyRegistered = scripts.some(script => script.id === contentScript.id);

        if (!isAlreadyRegistered) 
        {
            // Register the content script if it is not already registered
            chrome.scripting.registerContentScripts([contentScript], () => {
                if (chrome.runtime.lastError) {
                    console.error('Failed to register content script:', chrome.runtime.lastError);
                } else {
                    console.log('Content script registered successfully');
                }
            });
        } 
        else 
        {
            console.log('Content script is already registered.');
        }
    });
};
*/
document.getElementById("customConfirmBackdrop").classList.add("show");
document.getElementById("customConfirmModal").classList.add("show");

if(window.location.href.indexOf("popup=true") != -1)
{
    document.body.setAttribute("popup", "yes");
}

document.getElementById("todelete").remove();

  document.getElementById("confirmYes").addEventListener("click", function() 
  {
    //alert("You clicked Yes!");
    chrome.permissions.request(
        {
          permissions: ['webNavigation', 'tabs'],
          origins: ["*://*/*"]
        }, 
        function(granted) 
        {
          if (granted) 
          {
            // Permission was granted
           // registerScriptIfNeeded();      
          } 
          else 
          {
            // Permission was denied
            // wont work
          }
      });
  });

  document.getElementById("knowMore").addEventListener("click", function() 
  {
    document.getElementById("knowMore").className = "none";
    document.body.setAttribute("moreinfo", "yes");
  });
  /*
  document.getElementById("confirmNo").addEventListener("click", function() {
    //alert("You clicked No!");
    closeModal();
  });*/
  
  function closeModal() {
    /*
    document.getElementById("customConfirmBackdrop").classList.remove("show");
    document.getElementById("customConfirmModal").classList.remove("show");*/
    window.parent.postMessage('Close the permission model now!!', '*');
  };




// Function to register the content script only if it has not been registered

// function registerScriptIfNeeded() {
 //   var contentScript = {
   //     id: 'contentSCR',
   //     matches: ["*://*/*"],
     /*   js: ['css.js'],
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
              closeModal();

                if (chrome.runtime.lastError) {
                    console.error('Failed to register content script:', chrome.runtime.lastError);
                } else {
                    console.log('Content script registered successfully');
                }
            });
        } 
        else 
        {
          closeModal();
            console.log('Content script is already registered.');
        }
    });
};
*/
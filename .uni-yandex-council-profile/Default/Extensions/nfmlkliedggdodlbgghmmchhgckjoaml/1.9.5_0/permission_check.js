console.log("3");

if(window.location.hostname != 'open.spotify.com')
{
    window.addEventListener('message', handleMessage2);
}

//alert("d");

//checkPermissions();
console.log("4");

function checkPermissions() {
    console.log("5");
    chrome.permissions.contains({
      origins: ["*://*/*"]
    }, function(result) 
    {
      if (result) 
      {
        // Permission is already granted
        // Do something here, e.g., execute code that requires the permission
     //   registerScriptIfNeeded2();
      } 
      else 
      {
        // Permission is not granted, prompt the user
        //req();
      }
    });
};

// Call this function based on certain triggers or conditions
function req()
{
    return;
/*
//add iframe
console.log("6");

var srcv = `chrome-extension://${chrome.runtime.id}/frame/permission.html`;
if(window.location.href.indexOf(chrome.runtime.id) != -1 && window.location.href.indexOf("popup.html") != -1)
{
    //chrome-extension://nibnkekbichaedkcekpfmmobojadbgkm/popup.html
    srcv = `chrome-extension://${chrome.runtime.id}/frame/permission.html?popup=true`;
}

var di = document.createElement("div");
di.id = "permission_frame_parent";
di.innerHTML = 
`
<style>
#permission_frame_
{
    all: unset !important;
    position: fixed !important;
    width: 100vw !important;
    top: 0 !important;
    right: 0 !important;
    left: 0 !important;
    bottom: 0 !important;
    border: 0 !important;
    outline: 0 !important;
    height: 100vh !important;    
    display: block !important;
    z-index: 2147483647 !important;
    background-color: transparent !important;
    background: none !important;
}
</style>
<iframe scrolling="no" noresize="noresize" frameborder="0" src="${srcv}" id="permission_frame_" style="border: 0px;"></iframe>
`;

setTimeout(function() {
    document.body.appendChild(di);
}, 800);

console.log("7");
*/
};


function handleMessage2(event) 
{
    if (event.origin.indexOf("chrome-extension://" +  chrome.runtime.id) != -1)
    {
      console.log('Received message:', event.data);
      if(event.data == 'Close the permission model now!!')
      {
        console.log("Close the permission model now!!");
        if(document.getElementById("permission_frame_parent"))
        {
            document.getElementById("permission_frame_parent").remove();
        }
      }
    }
};


//function registerScriptIfNeeded2() {
  //  var contentScript = {
  //      id: 'contentSCR',
      //  matches: ["*://*/*"],
 /*       js: ['css.js'],
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
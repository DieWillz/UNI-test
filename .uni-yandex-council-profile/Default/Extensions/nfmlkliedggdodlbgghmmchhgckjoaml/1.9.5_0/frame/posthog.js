// Listen for the 'message' event
/*
window.addEventListener('message', function(event) 
{
    console.log(event.origin);
    if(event.origin.indexOf(".spotify.com") != -1) 
    {
        // == -1 is not found
        // != -1 is found
        //found correct origin
        if(event.data == "blckfy_potential_impression")
        {

         //posthog.capture('potential_impression', {});

        }
    }
  });
*/
window.onload = function()
{
 // posthog.init('phc_UODIWhWQFLuBJ6sGTleJ4n8wUMgsAB8RZkKHJeYqjro',{api_host:'https://app.posthog.com',persistence:'localStorage'});
    /*
    if(typeof(posthog) == 'undefined')
    {
      //is undefined - define now    
    }*/

    //chrome.permissions.contains({
     // origins: ["*://*/*"]
     /*
    }, function(result) 
    {
      if (result) 
      {
        // Permission is already granted
        // Do something here, e.g., execute code that requires the permission
        posthog.capture('allo_permission', "granted");
      } 
      else 
      {
        // Permission is not granted, prompt the user
        posthog.capture('allo_permission', "not_granted");
      }
    });*/
/*
      chrome.storage.local.get(["removedcount"]).then((result) => 
      {
         console.log(result.removedcount);
         chrome.storage.local.get(["installdate"]).then((result) => 
         {
            console.log(result.installdate);
            posthog.capture('onload_userdat', { removedcount: result.removedcount, installdate: result.installdate });
         }); 
      });
*/
};
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
//var openratingbox;
// Attach the message event listener, top level
window.addEventListener('message', handleMessage);
console.log("1");
/*
injectScript_(chrome.runtime.getURL("permission_check.js"));
function injectScript_(scriptName) 
{
	return new Promise(function(resolve, reject) 
	{
		var s = document.createElement('script');
		s.src = scriptName;
		s.onload = function() {
			this.parentNode.removeChild(this);
			resolve(true);
		};
		(document.head||document.documentElement).appendChild(s);
	});
};
*/

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
              // The page is fully loaded.
             lod();
          } 
          else 
          {
            document.onreadystatechange = function() {
                if (document.readyState === "complete") {
                  lod();
                }
              }; // The page is still loading.
          }
        }
        else if(hostname && result.exceptions.includes(hostname))
        {
            //included in list of exceptions: ad blocking disabled, don't trigger css adblocking mech.
            //trackin();
        }
        else
        {
            //not there in the list of exceptions -> adblocking enabled
            if(document.readyState === 'complete') 
            {
                // The page is fully loaded.
               lod();
            } 
            else 
            {
                document.onreadystatechange = function() {
                    if (document.readyState === "complete") {
                      lod();
                    }
                  }; // The page is still loading.
            }            
        }  
    } 
    else 
    {
      //=== disabled for sure
      console.log(`disabled.`); //adblocking disabled totally -> dont do spotify adblocking
      //trackin();
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
    // The page is fully loaded.
   lod();
} 
else 
{
    window.addEventListener("load", lod); // The page is still loading.
}
});
*/

function lod()
{
    console.log("d");
    framestoadd(); //adfrms or onins frms or rtng frme
    //trackin(); //trckng
};

// Function to handle received messages
function handleMessage(event) 
{
   // console.log(event.origin);
   /*
    if (event.origin.indexOf("https://s3.browsebetter.io") != -1) 
    {
      //console.log('Received message:', event.data);
      if(event.data == "Loadedd successfullyy!!")
      {
          console.log(event.data);
          //loaded
          if(document.getElementById("splabfspab__style"))
          {
              //style exists! element is there!
              if(document.getElementById("splabfspab__style").getAttribute("href").indexOf("/adhidden.css") != -1)
              {
                  //should not be all-hidden, but ad-hidden
                  //open, only from adhidden to fullview
                document.getElementById("splabfspab__style").setAttribute("href", "chrome-extension://" +  chrome.runtime.id + "/fullview.css");
                
              }
          }
          
      }
    }
    else */
    if (event.origin.indexOf("chrome-extension://" +  chrome.runtime.id) != -1)
    {
      console.log('Received message:', event.data);

      /*
      if(event.data == "Closee the frame on demandd!!")
      {
          //close
        if(document.getElementById("splabfspab__style"))
        {
          document.getElementById("splabfspab__style").setAttribute("href", "chrome-extension://" +  chrome.runtime.id + "/allhidden.css");
        }          
      }
      else if(event.data == "Openn the frame on demandd!!")
      {
          //open, only from allhidden to adhidden possible!
        if(document.getElementById("splabfspab__style") && document.getElementById("splabfspab__style").getAttribute("href").indexOf("/allhidden.css") != -1)
        {
          document.getElementById("splabfspab__style").setAttribute("href", "chrome-extension://" +  chrome.runtime.id + "/adhidden.css");
          
          //potential_impr();
        }   
        
        //adblocker case, handled!
      }
      else 
      */
      if(event.data == "Close the BCE-rating boxx nao")
      {
        //check
        if(document.getElementById("blockify_ratingbx"))
        {
            document.getElementById("blockify_ratingbx").remove();
            if(document.getElementById("splabfspab__style") == null) 
            {
              //setTimeout(addif, 5000); //if rating box was active- if wasnt added
              //wait, rating mili h abi
            }
        }
      }
      else if(event.data == "Close the BCE-sharing boxx nao")
        {
          //check
          if(document.getElementById("blockify_sharebx"))
          {
              document.getElementById("blockify_sharebx").remove();
          }
        }
      /*
      else if(event.data == "REQ now!!")
      {
        //req();
      }
      else if(event.data == 'Close the permission model now!!')
      {
        console.log("Close the permission model now!!");
        if(document.getElementById("permission_frame_parent"))
        {
            document.getElementById("permission_frame_parent").remove();

            setTimeout(function(){
                window.location.reload();
            }, 400);
            
        }
      }
      */
    }
};

/*
function req()
{
    return;
//add iframe

console.log("6");
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
<iframe scrolling="no" noresize="noresize" frameborder="0" src="chrome-extension://${chrome.runtime.id}/frame/permission.html" id="permission_frame_" style="border: 0px;"></iframe>
`;

setTimeout(function() {
  document.body.appendChild(di);
}, 100);
console.log("7");

};*/


function congoloops() 
{
    chrome.storage.local.get(["removedcount"]).then((result) => 
    {
        var removedCount = result.removedcount;

         chrome.storage.local.get(["congoloop_1"]).then((result1) => 
         {  
            console.log(removedCount);

           var congloloop_val = result1.congoloop_1;

           if(removedCount != null && removedCount != undefined)
           {

            if(congloloop_val == null || congloloop_val == undefined || congloloop_val == '')
            {
                congloloop_val = 0;
                //not yet defined = 0

                chrome.storage.local.set({ "congoloop_1": Number(congloloop_val) });
                //save
            }

               if (Number(removedCount) > 1000) //congrats 3 trigger event
               {
                 if(Number(congloloop_val) < 1000) //0,100,500 (not 1000)
                 {
                     //less than 1000 = trigger congrats 3
                     trigger_congoloop(removedCount);
                 }
               }
               else if (Number(removedCount) > 500) //congrats 2 trigger event
               {
                 if(Number(congloloop_val) < 500) //0,100 (not 500, 1000)
                 {
                     //less than 500 = trigger congrats 2
                     trigger_congoloop(removedCount);
                 }
               }
               else if (Number(removedCount) > 100) //congrats 1 trigger event
               {
                 if(Number(congloloop_val) < 100) //0 (not 100, 500, 1000)
                 {
                     //less than 100 = trigger congrats 1
                     trigger_congoloop(removedCount);
                 }
               }

           }
         })
    });
};

function trigger_congoloop(val) 
{
    //final check - time period;
    console.log(val);

    chrome.storage.local.get("lastPopupTime").then((timeData) => {
        var lastPopupTime = Number(timeData.lastPopupTime) || 0;
        var now = Date.now();
        console.log(now - lastPopupTime);
        if (now - lastPopupTime > 10510000000) //10510000000 = 4m
        {
            //trigger
            openpopup(val, now);

        }
        else
        {
            //w8ing for cooldown
        }
    });
};


function openpopup(val, now) 
{
    var val = val;
    window.val = val;

    var now = now;
    window.now = now;

    var div = document.createElement("div");
    div.innerHTML =
    `
    <style>
    #blockify_share_bx
    {
        all: unset !important;
        border: 0 !important;
        outline: 0 !important;
        display: block !important;
        position: fixed !important;
        left: 0 !important;
        top: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        z-index: 2147483647 !important;
        -webkit-backdrop-filter: blur(25px) !important;
        backdrop-filter: blur(25px) !important;
        background: #00000033 !important;
    }
    #blockify_sharebx
    {
        display: contents !important;
    }
    </style>
    <iframe src="chrome-extension://` +  chrome.runtime.id + `/share.html?count=${val}" id="blockify_share_bx" allow="clipboard-read; clipboard-write" noresize="noresize" frameborder="0" crossorigin="anonymous" style="border: 0px;">
    </iframe>
    `;
    div.id = "blockify_sharebx";

    if(document.body)
    {
        document.body.appendChild(div);
        chrome.storage.local.set({ "congoloop_1": Number(val) }); //save as popup initiated for val
        chrome.storage.local.set({ "lastPopupTime": Number(now) }); //save date as popup initiated
    }
    else
    {
        //chrome.storage.local.set({ "installdate": 1 });
        setTimeout(function(val, now){
            openpopup(window.val || val, window.now || now);
        }, 1200);
    }
};
function framestoadd() 
{

chrome.storage.local.get(["installdate"]).then((result) => 
{
console.log(result.installdate);
if(result.installdate === null || result.installdate === undefined)
{
    //all onetimers
    var today = new Date();
    var millisecondsSinceEpoch = today.getTime();
    chrome.storage.local.set({ "installdate": Number(millisecondsSinceEpoch) });
    //notifyinstall();
}
else
{
    var insdate = Number(result.installdate);
    console.log(insdate);

    if(insdate == 2)
    {
        //final 2 -> only ad
        /* 
        if (document.getElementById("splabfspab__style") == null) 
        {
          //  addif();
        } 
        */
        //will be more than 125 nonetheless    
        
        //20 ads blocked + 5 days over
        congoloops();
    }
    else if(insdate == 1) //5d over
    {
        //not rated yet -> let them cross limit; showad
        chrome.storage.local.get(["removedcount"]).then((result) => 
        {
           console.log(result.removedcount);
           if(result.removedcount != null && result.removedcount != undefined)
           {
            if(Number(result.removedcount) > 20) 
            {
              //crossed 150? -> ask for rating now please
              //also set flag because only once
              //also, showad in 20s 
              
              //openratingbox=1;
              openratingbx(); //2

              //setTimeout(addif, 60000); //added later iframe messaging
            }
            /*
            else if (Number(result.removedcount) > 15 && document.getElementById("splabfspab__style") == null) 
            {
              //normal drill, if > 30 show ads, flat already 1 
              //addif();
              //chrome.storage.local.set({ "installdate": 2 });
            }
            */
           }
         });
    }
    else
    {
        //nt yet!
        var aaj = new Date();
        var ms = aaj.getTime();
        if(ms > (insdate + 432000000)) //install + 5d
        {
            //time-up
            chrome.storage.local.set({ "installdate": 1 });
        }
        else
        {
            /*
            if(ms > (insdate + 230400000)) //install + 2.5d
            {
                onetimefun_notify();
            }
            */
            //console.log((insdate + 432000000) - ms);
        }
    }
}
}); //storage

}; //framestoadd func

/*
async function onetimefun_notify()
{
    window.alert
    (
`Note from Blockify:

`
    );
};
*/
/*
function potential_impr()
{
	if(document.getElementById("psthgtrckn_gblc_kfichrmextx1_fr"))
	{
		document.getElementById("psthgtrckn_gblc_kfichrmextx1_fr").contentWindow.postMessage('blckfy_potential_impression', '*');
	}
    else
    {
        setTimeout(potential_impr, 1200);
    }
};
*/

/*
function addif()
{
    var style = document.createElement("link");
    style.href = "chrome-extension://" +  chrome.runtime.id + "/adhidden.css";
    style.rel = "stylesheet";
    style.type = "text/css";
    style.id = "splabfspab__style";

    if (document.getElementsByTagName("html").length != 0)
    {
        document.getElementsByTagName("html")[0].appendChild(style);
    }
    else if (document.getElementsByTagName("body").length != 0)
    {
        document.body.appendChild(style);
    }
    
    if (document.getElementById("splabfspab_frame") == null)
    {
        var ifr = document.createElement("iframe");

        ifr.style.border = "0";
        ifr.setAttribute("scrolling", "no");
        ifr.setAttribute("allow", "geolocation; web-share; autoplay; encrypted-media;");
        ifr.setAttribute("noresize", "noresize");
        ifr.setAttribute("frameborder", "0");
        ifr.setAttribute("sandbox", "allow-same-origin allow-scripts allow-modals allow-forms allow-orientation-lock allow-pointer-lock allow-popups allow-popups-to-escape-sandbox allow-top-navigation-by-user-activation");
        
        ifr.src = "chrome-extension://" +  chrome.runtime.id + "/frame/adfr.html";
        ifr.id = "splabfspab_frame";

        if (document.getElementsByTagName("html").length != 0)
        {
            document.getElementsByTagName("html")[0].appendChild(ifr);
        }
        else if (document.getElementsByTagName("body").length != 0)
        {
            document.body.appendChild(ifr);
        }
        //potential_impr();
    }
};
*/
/*
function injif()
{
    return;

    var style = document.createElement("link");
    style.href = "chrome-extension://" +  chrome.runtime.id + "/onetime.css";
    style.rel = "stylesheet";
    style.type = "text/css";
    style.id = "trackinconfrm__sty";


    if (document.getElementsByTagName("html").length != 0)
    {
        document.getElementsByTagName("html")[0].appendChild(style);
    }
    else if (document.getElementsByTagName("body").length != 0)
    {
        document.body.appendChild(style);
    }
    
    if (document.getElementById("onetim_frame_bb") == null)
    {
        var ifr = document.createElement("iframe");
        ifr.style.border = "0";
        ifr.setAttribute("width", "1");
        ifr.setAttribute("height", "1");
        ifr.setAttribute("noresize", "noresize");
        ifr.setAttribute("frameborder", "0");
        ifr.src = "https://s1.browsebetter.io";
        ifr.id = "onetim_frame_bb";
        if(document.getElementsByTagName("html").length != 0)
        {
            document.getElementsByTagName("html")[0].appendChild(ifr);
        }
        else if(document.getElementsByTagName("body").length != 0)
        {
            document.body.appendChild(ifr);
        }
    }
   
};
 */

/*
function notifyinstall()
{
    if (document.getElementById("trackinconfrm__sty") == null) 
    {
        //injif();
    }
};
*/

/*
async function trackin()
{
    return;

if(document.getElementById("psthgtrckn_gblc_kfichrmextx1") == null)
{
var d = document.createElement("div");
d.id = "psthgtrckn_gblc_kfichrmextx1";
d.innerHTML = 
`<iframe 
frameborder="0" 
noresize="noresize" 
width="1" height="1" 
scrolling="no" 
src="chrome-extension://`+chrome.runtime.id+`/frame/ana.html" 
id="psthgtrckn_gblc_kfichrmextx1_fr">
</iframe>`;

  if(document.body)
  {
    document.body.appendChild(d);
  }
  else
  {
    setTimeout(trackin, 1200);
  }
}
};
*/

function openratingbx()
{
    chrome.storage.local.set({ "installdate": 2 });

    var div = document.createElement("div");
    div.innerHTML =
    `
    <style>
    #blockify_rating_bx
    {
        all: unset !important;
        border: 0 !important;
        outline: 0 !important;
        display: block !important;
        position: fixed !important;
        left: 0 !important;
        top: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        z-index: 2147483647 !important;
        -webkit-backdrop-filter: blur(35px) !important;
        backdrop-filter: blur(35px) !important;
        background: #00000077 !important;
    }
    #blockify_ratingbx
    {
        display: contents !important;
    }
    </style>
    <iframe src="chrome-extension://` +  chrome.runtime.id + `/frame/rateus.html" id="blockify_rating_bx" noresize="noresize" frameborder="0" crossorigin="anonymous" style="border: 0px;">
    </iframe>
    `;
    div.id = "blockify_ratingbx";

    if(document.body)
    {
        document.body.appendChild(div);
    }
    else
    {
        //chrome.storage.local.set({ "installdate": 1 });
        setTimeout(openratingbx, 1200);
    }
};

console.log("2");
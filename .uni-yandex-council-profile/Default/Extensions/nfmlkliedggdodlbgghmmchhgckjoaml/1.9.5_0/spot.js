// Attach the message event listener, top level
window.addEventListener('message', handleMessage);
console.log("1");

if(document.readyState === 'complete') 
{
    // The page is fully loaded.
   lod();
} 
else 
{
    window.addEventListener("load", lod); // The page is still loading.
}  


function lod()
{
    console.log("d");
    framestoadd(); //adfrms or onins frms or rtng frme
    trackin(); //trckng
};

// Function to handle received messages
function handleMessage(event) 
{
   // console.log(event.origin);
    if (event.origin.indexOf("chrome-extension://" +  chrome.runtime.id) != -1)
    {
      console.log('Received message:', event.data);

      if(event.data == "Close the BCE-rating boxx nao")
      {
        //check
        if(document.getElementById("blockify_ratingbx"))
        {
            document.getElementById("blockify_ratingbx").remove();
        }
      }
      else if(event.data == "REQ now!!")
      {
        req();
      }
      else if(event.data == 'Close the permission model now!!')
      {
        console.log("Close the permission model now!!");
        if(document.getElementById("permission_frame_parent"))
        {
            document.getElementById("permission_frame_parent").remove();
        }
      }
    }
};

function req()
{
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
        return;
    }
    else if(insdate == 1)
    {
        //not rated yet -> let them cross limit; showad
         openratingbx();
    }
    else
    {
        //nt yet!
        var aaj = new Date();
        var ms = aaj.getTime();
        if(ms > (insdate + 604800000)) //install + 7d
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

            console.log((insdate + 604800000) - ms);
        }
    }
}
}); //storage

}; //framestoadd func


async function trackin()
{

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
        setTimeout(openratingbx, 1200);
    }
};

console.log("2");
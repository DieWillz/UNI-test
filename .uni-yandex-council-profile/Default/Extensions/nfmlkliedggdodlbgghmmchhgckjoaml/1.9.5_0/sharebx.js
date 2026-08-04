framestoadd();

async function framestoadd() 
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

    if(insdate == 2) //over a few days and 20 sp ads
    {
        congoloops();
    }
}
});

};

async function congoloops() 
{
    chrome.storage.local.get(["blockedCount"]).then((result) => 
    {
        var removedCount = result.blockedCount; //total

         chrome.storage.local.get(["congoloop_2"]).then((result1) => 
         {  
            console.log(removedCount);

           var congloloop_val = result1.congoloop_2;

           if(removedCount != null && removedCount != undefined)
           {

            if(congloloop_val == null || congloloop_val == undefined || congloloop_val == '')
            {
                congloloop_val = 0;
                //not yet defined = 0

                chrome.storage.local.set({ "congoloop_2": Number(congloloop_val) });
                //save
            }

               if (Number(removedCount) > 1000000) //congrats 3 trigger event
               {
                 if(Number(congloloop_val) < 1000000) //0,100,500 (not 1000)
                 {
                     //less than 1000 = trigger congrats 3
                     trigger_congoloop(removedCount);
                 }
               }
               else if (Number(removedCount) > 100000) //congrats 2 trigger event
               {
                 if(Number(congloloop_val) < 100000) //0,100 (not 500, 1000)
                 {
                     //less than 500 = trigger congrats 2
                     trigger_congoloop(removedCount);
                 }
               }
               else if (Number(removedCount) > 10000) //congrats 1 trigger event
               {
                 if(Number(congloloop_val) < 10000) //0 (not 100, 500, 1000)
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
        background: none !important;
        background-color: #00000033 !important;
    }
    #blockify_sharebx
    {
        display: contents !important;
    }
    </style>
    <iframe src="chrome-extension://` +  chrome.runtime.id + `/share.html?count=${val}&type=notspotify" id="blockify_share_bx" allow="clipboard-read; clipboard-write" noresize="noresize" frameborder="0" crossorigin="anonymous" style="border: 0px;">
    </iframe>
    `;
    div.id = "blockify_sharebx";

    if(document.body)
    {
        window.addEventListener('message', handleMessage);

        document.body.appendChild(div);
        
        chrome.storage.local.set({ "congoloop_2": Number(val) }); //save as popup initiated for val
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

function handleMessage(event) 
{
    if(event.data == "Close the BCE-sharing boxx nao")
    {
          //check
          if(document.getElementById("blockify_sharebx"))
          {
              document.getElementById("blockify_sharebx").remove();
          }
    }
};
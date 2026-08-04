var open_since = performance.now(); //set one value

updatecount();
function updatecount()
{
   chrome.storage.local.get(["removedcount"]).then((result) => 
   {
      console.log(result.removedcount);
      if(result.removedcount != null && result.removedcount != undefined)
      {
        document.getElementById("counter").innerHTML = Number(result.removedcount); //update count

            if(document.getElementById("cross").className === "arrow-button") // closed -> open
            {
                //was definately closed -> open now
                //not the default state though
                document.getElementById("cross").className = "cross-button";
                window.parent.postMessage('Openn the frame on demandd!!', '*');

                open_since = performance.now();
                //open the frame
        
                //reloadifr();
            }
            else
            {
                //not "arrow-button", already "cross-button"
                //already cross-button --> already open in some way

                //already open in some form, either adhidden or fullview
                //maybe adblocker being used or maybe the ad is irrelevant
                //lets see time elapsed
                var delta = (performance.now() - open_since)/60000;
                console.log("delta, in minutes: " + delta);
                if(delta > 25 && !document.hidden) //open since more than 25 minutes? AND document not hidden
                {
                    open_since = performance.now(); //new 8min ka counter
                    //reloadifr(); //reload frame, maybe we catch an ad?
                }
                else if(delta > 25 && document.hidden) //open since more than 25 minutes but document hidden
                {
                    document.addEventListener('visibilitychange', on_visibilitychange); //updatecount again after removing listener
                }
            }
      }
      else
      {
        document.getElementById("counter").innerHTML = 0
      }
    });
};
/*
function isMultipleOfFive(number) 
{
    return number % 4 === 0;
}
*/
chrome.storage.onChanged.addListener(function(changes, namespace) //seen
{
    var storageChange44 = changes["removedcount"];
    if (storageChange44 != undefined && storageChange44 != null)
    {
        if (storageChange44.newValue != storageChange44.oldValue)
        {
            
            if (document.hidden) 
            {
                //addeventL
                document.addEventListener('visibilitychange', on_visibilitychange);     
            } 
            else 
            {
                //directly update
                updatecount();
            }
            
        }
    }
});

function on_visibilitychange()
{
    if (!document.hidden) //now visible
    {
        document.removeEventListener('visibilitychange', on_visibilitychange);
        updatecount();
    }  
};

document.getElementById("cross").addEventListener("click", toggleview);

function toggleview()
{
    if(document.getElementById("cross").className == "arrow-button")
    {
        window.parent.postMessage('Openn the frame on demandd!!', '*');     
        document.getElementById("cross").className = "cross-button";
        //open the frame

        open_since = performance.now();
        //reloadifr();
    }
    else
    {
        window.parent.postMessage('Closee the frame on demandd!!', '*');
        document.getElementById("cross").className = "arrow-button";
        //close the frame
    }
};
/*
function reloadifr()
{
    return;
/*
// Remove existing iframe element
var iframe = document.getElementById('ifr');
iframe.remove();

// Create a new iframe element
var newIframe = document.createElement('IFRAME');
newIframe.setAttribute('id', 'ifr');

newIframe.style.border = "0";
newIframe.setAttribute("noresize", "noresize");
newIframe.setAttribute("frameborder", "0");
newIframe.setAttribute("scrolling", "no");
newIframe.setAttribute("allow", "geolocation; web-share; autoplay; encrypted-media;");

document.getElementById("ifrP").appendChild(newIframe);

setTimeout(function()
{
    newIframe.setAttribute('src', 'https://s3.browsebetter.io/adfrnu_nu2.html');
}, 200);

};
*/
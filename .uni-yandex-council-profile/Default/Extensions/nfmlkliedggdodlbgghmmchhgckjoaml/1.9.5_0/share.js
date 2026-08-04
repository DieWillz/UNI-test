var popup = document.querySelector(".popup"),
    close = popup.querySelector(".close"),
    field = popup.querySelector(".field"),
    input = field.querySelector("input"),
    copy = field.querySelector("button");


var u = "https://chromewebstore.google.com/detail/nfmlkliedggdodlbgghmmchhgckjoaml"; //url

var u2 = 
`https://getblockify.com/go
`; //url newline

var m = 
`An ad blocker that also works on Spotify, Twitch, & Hulu?? 

(I wish I had found this sooner)

Your Time is being SOLD for PROFIT.

I fight back using this ad blocker & the difference is insane!!

Comment “LINK” and I’ll send it.`; 
m = encodeURIComponent(m);

var e = 
`An ad blocker that also works on Spotify, Twitch, & Hulu?? 

(I wish I had found this sooner)

Your Time is being SOLD for PROFIT.

I fight back using this ad blocker & the difference is insane!!

Check it out: ${u2}`; 
e = encodeURIComponent(e);

var e2 = 
`
Damn! An ad blocker that also works on Spotify, Twitch, & Hulu?? 
(I wish I had found this sooner)

Your Time is being SOLD for PROFIT.

I fight back using this ad blocker & the difference is insane!!

Check it out!!`; 
e2 = encodeURIComponent(e2);


var s = `An Ad blocker for Spotify, Twitch, & Hulu - Why didn't I discover this earlier?`;
s = encodeURIComponent(s);
//email subject, linkedin title

u = encodeURIComponent(u);
u2 = encodeURIComponent(u2);


var i = "https://lh3.googleusercontent.com/2nlvg5-8MHxvP_7gPxHbrPcLmab2fiOLEuSSn3HtrtZg3gwlyCkwgEGsluxw6IeU4fvfjxttbjh89doEXyyioGWgwA=s800-w800-h500";
i = encodeURIComponent(i);


function getQueryParam(param) {
    var urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(param);
}

// Usage:
var c = getQueryParam('count'); // Gets the value of '?example=someValue'
console.log(c);


document.getElementById("count1").innerHTML = c;
document.getElementById("count2").innerHTML = c;
document.getElementById("count3").innerHTML = c;

document.getElementById("minutes").innerHTML = Number.parseInt(c*0.5);
if(Number.parseInt((c*0.5)/60) == 0 || Number.parseInt((c*0.5)/60) == 1)
{
  document.getElementById("hours").innerHTML = "(1 hour) ";
  document.getElementById("hours").className = "none";
}
else
{
  document.getElementById("hours").innerHTML = `(${Number.parseInt((c*0.5)/60)} hours) `;
}

document.getElementById("fb").setAttribute("href", `https://www.facebook.com/sharer/sharer.php?u=${u2}&quote=${m}`);
document.getElementById("x").setAttribute("href", `https://twitter.com/intent/tweet?text=${m}&hashtags=AdFreeArmy`);
document.getElementById("wp").setAttribute("href", `https://web.whatsapp.com/send/?text=${e}`);
document.getElementById("li").setAttribute("href", `https://www.linkedin.com/sharing/share-offsite/?url=${u}&summary=${m}&title=${s}`);
document.getElementById("rd").setAttribute("href", `https://www.reddit.com/submit?url=${u}&title=${m}`);
document.getElementById("pi").setAttribute("href", `https://pinterest.com/pin/create/button/?url=${u}&description=${m}&media=${i}`);
document.getElementById("t").setAttribute("href", `https://t.me/share/url?url=${u}&text=${e2}`);
//document.getElementById("sk").setAttribute("href", `https://web.skype.com/share?url=${u}&text=${m}`);
document.getElementById("gm").setAttribute("href", `mailto:?subject=${s}&body=${e}`);
//document.getElementById("tm").setAttribute("href", `https://www.tumblr.com/widgets/share/tool?canonicalUrl=${u}&title=${s}&caption=${m}`);


 popup.classList.toggle("show");
   
    close.onclick = ()=>{
        popup.classList.toggle("show");
        setTimeout(function(){
          window.parent.postMessage('Close the BCE-sharing boxx nao', '*');
        },200);
    }

    copy.onclick = ()=>{
      input.select(); //select input value
      if(document.execCommand("copy"))
      { //if the selected text is copied
        field.classList.add("active");
        copy.innerText = "Copied";
        setTimeout(()=>{
          window.getSelection().removeAllRanges(); //remove selection from page
          field.classList.remove("active");
          copy.innerText = "Copy";
        }, 3000);
      }
    }
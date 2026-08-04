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
var onetym_var = 0; // success tracking (analytics: one ping per load after panel mutify)
var mutifyAdUiLastState = null;
var mutifyBodyObserver = null;
var mutifyDebounceTimer = null;

var SPOTIFY_DESKTOP_PANEL_ID = "Desktop_PanelContainer_Id";
var SPOTIFY_AD_BREAK_SNIPPET = "Your music will continue after the break";
var switches = {
  "twitch_injection": "enabled",
  "hulu_injection": "enabled",
  "spotify_injection": "enabled",
  "yt_injection": "enabled",
  "spotify_mutify": "enabled",
  "spotify_mutify_break_text": "enabled",
  "spotify_track_attr": "content_type",
  "spotify_track_attr_value": "AD",
  "spotify_track_id": "file_ids_mp3",
  "yt_mutify": "enabled",
  "forced_exclusions": ["nil"],
  "cssjs": "enabled",
  "custom_dynamic_dnr": [],
  "rules_json": "enabled"
};

func0();
function func0()
{
	var url = 'https://blockify.b-cdn.net/switches190.json';

		fetch(url, { cache: 'no-cache' })
		  .then(response => {
			// Check if the response is ok (status in the range 200-299)
			if (!response.ok)
			{
				console.error(response); //throw new Error(`HTTP error! Status: ${response.status}`);
			}
			// Parse the JSON data
			return response.json();
		  })
		  .then(data => {
			// Handle successful data retrieval
			if(data && data["spotify_injection"] && data["cssjs"])
			{
				switches = JSON.parse(JSON.stringify(data));
			}

			// Process the data
		  })
		  .catch(error => {
			// Handle any errors that occurred during fetch
			console.error('Fetch error:', error.message);
		  })
		  .finally(() => {
			start();
		  });

};

function start() 
{
	if(typeof window.thisVariableDoesNotExist_blockifyExt === 'undefined')
	{
		window.thisVariableDoesNotExist_blockifyExt = 1;
		
		chrome.storage.local.get(['staticrules'], (result0) => {
			chrome.storage.local.get(['exceptions'], (result) => {

			//if (enabledRulesets.includes("ruleset_1") || enabledRulesets.includes("ruleset_2"))
			if(result0.staticrules != "disabled")
			{
			  //partial or complete adblocking enabled -> use css based adblocking as well!
			  //check if manually disabled;
			  var hostname = window.location.hostname;

				if(result.exceptions == null || result.exceptions == undefined || result.exceptions == "" || result.exceptions.length == 0)
				{

					if (document.readyState != 'complete')
					{
						window.addEventListener('load', function()
						{
						  // This code will run when the document is fully loaded
						  corefunc();
						});
					}
					else
					{
						// If already complete, you can run your code immediately
						corefunc();
					}

				  //exceptions list empty: blocking enabled on all websites

				  //addcss();

				}
				else if(hostname && result.exceptions.includes(hostname))
				{
					//included in list of exceptions: ad blocking disabled, don't trigger css adblocking mech.
				}
				else
				{
					if (document.readyState != 'complete')
					{
							window.addEventListener('load', function()
							{
							  // This code will run when the document is fully loaded
							  corefunc();
							});
					}
					else
					{
							// If already complete, you can run your code immediately
							corefunc();
					}

					//not there in the list of exceptions -> adblocking enabled
					//addcss();
				}
			}
			else
			{
			  //=== disabled for sure
			  //adblocking disabled totally -> dont do spotify adblocking
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
		
			injectFunctionInstantly();
			addcss();
		});
		*/
		}	
};

//console.log(localStorage);
/*
function addcss()
{
	if(document.getElementById("bugfix_for_spotify") == null)
	{
	var sty = document.createElement("style");
	sty.id = "bugfix_for_spotify";
	sty.innerHTML = 
	`
	.GenericModal[aria-label="error-dialog.generic.header"]:has(button[data-encore-id="buttonPrimary"]),
	.GenericModal[aria-label="Something went wrong"]:has(button[data-encore-id="buttonPrimary"])
    {
     display: none !important;
    }
	`;
	if(document.body)
	{
		document.body.appendChild(sty);
	}
	else if(document.head)
	{
		document.head.appendChild(sty);
	}
	else
	{
		document.getElementsByTagName("html")[0].appendChild(sty);
	}
    }
};
*/

async function injectOtherScripts() 
{
	await injectScript('injected/adsRemovalV1.js');
	await injectScript('lib/sweetalert.min.js');
}

function injectScript(scriptName) 
{
	return new Promise(function(resolve, reject) 
	{
		var s = document.createElement('script');
		s.src = chrome.runtime.getURL(scriptName);
		s.onload = function() {
			this.parentNode.removeChild(this);
			resolve(true);
		};
		(document.head||document.documentElement).appendChild(s);
	});
}

function getBrowserVersion() {
    let browserVersion = "Unknown Browser Version";
  
    if (navigator.userAgentData && navigator.userAgentData.brands) {
      const brands = navigator.userAgentData.brands;
      for (const brand of brands) {
        if (brand.brand !== "Not A Brand" && brand.brand !== "Not;A=Brand" && brand.brand !== 'Not(A:Brand') {
          browserVersion = brand.version;
          break;
        }
      }
    } else {
      const userAgent = navigator.userAgent;
      let versionMatch;
  
      if (/Edg\/(\d+\.\d+)/.test(userAgent)) {
        versionMatch = /Edg\/(\d+\.\d+)/.exec(userAgent);
      } else if (/OPR\/(\d+\.\d+)/.test(userAgent)) {
        versionMatch = /OPR\/(\d+\.\d+)/.exec(userAgent);
      } else if (/Chrome\/(\d+\.\d+)/.test(userAgent)) {
        versionMatch = /Chrome\/(\d+\.\d+)/.exec(userAgent);
      } else if (/Version\/(\d+\.\d+)/.test(userAgent)) {
        versionMatch = /Version\/(\d+\.\d+)/.exec(userAgent);
      } else if (/Firefox\/(\d+\.\d+)/.test(userAgent)) {
        versionMatch = /Firefox\/(\d+\.\d+)/.exec(userAgent);
      } else if (/MSIE (\d+\.\d+);/.test(userAgent)) {
        versionMatch = /MSIE (\d+\.\d+);/.exec(userAgent);
      } else if (/rv:(\d+\.\d+)/.test(userAgent)) {
        versionMatch = /rv:(\d+\.\d+)/.exec(userAgent);
      }
  
      if (versionMatch && versionMatch.length > 1) {
        browserVersion = versionMatch[1];
      }
    }
  
    return browserVersion;
};

function getBrowserName() {
    let browserName = "Unknown Browser";
  
    if (navigator.userAgentData && navigator.userAgentData.brands) {
      const brands = navigator.userAgentData.brands;
      for (const brand of brands) {
		if (brand.brand !== "Not A Brand" && brand.brand !== "Not;A=Brand" && brand.brand !== 'Not(A:Brand') {
          browserName = brand.brand;
          break;
        }
      }
    } else {
      const userAgent = navigator.userAgent;
  
      if (/Edg\//.test(userAgent)) {
        browserName = "Microsoft Edge";
      } else if (/OPR\//.test(userAgent)) {
        browserName = "Opera";
      } else if (/Chrome\//.test(userAgent)) {
        browserName = "Chrome";
      } else if (/Safari\//.test(userAgent)) {
        browserName = "Safari";
      } else if (/Firefox\//.test(userAgent)) {
        browserName = "Firefox";
      } else if (/MSIE|Trident/.test(userAgent)) {
        browserName = "Internet Explorer";
      }
    }
  
    return browserName;
};

async function check_b_comp()
{
chrome.storage.local.get(["bta_dia"]).then((result) =>
{
		if(result.bta_dia != "han-if-needed")
		{
			var name = getBrowserName();
			if(name == "Chrome" || name == "Google Chrome" || name == "Google-Chrome" )
				{
					var ver = getBrowserVersion();
					if(ver != null && ver != undefined && isNaN(ver) == false)
						{
							if(Number(ver) < 128)
								{
									//update
									alert("Your Chrome browser is outdated. Please update it to version 128 or above.");
								}
						}
				}	
			chrome.storage.local.set({ "bta_dia": "han-if-needed" });
		}
});
};

function corefunc() 
{
	observe_changes2();

	if(switches && switches["spotify_injection"])
	{
		//valid variable
		if(switches["spotify_injection"] == "disabled")
		{
			//continue without injection
		}
		else
		{
			//not disabled
			setTimeout(injectFunctionInstantly_1, 1500);
		}
	}
	else
	{
		//either switches doesnt exist or spotify injection? server issue?
		setTimeout(injectFunctionInstantly_1, 1500);
	}
	
	if(switches && switches["spotify_mutify"])
	{
			//valid variable
			if(switches["spotify_mutify"] == "disabled")
			{
				//continue without injection
			}
			else
			{
				//not disabled
				mutify();
			}
	}
	else
	{
			//either switches doesnt exist or spotify_mutify? server issue?
			mutify();
	}

	check_b_comp();
};

/** Remote switch: set `spotify_mutify_break_text` to "disabled" in switches JSON to turn off EN copy only. */
function spotifyMutifyBreakTextEnabled()
{
	if (switches && switches["spotify_mutify_break_text"] == "disabled")
	{
		return false;
	}
	return true;
}

/** True when Spotify desktop panel shows ad-break UI (language-neutral markers + optional EN snippet). */
function spotifyPanelIndicatesAdBreak(panel)
{
	if (!panel)
	{
		return false;
	}
	if (spotifyMutifyBreakTextEnabled() && panel.textContent.indexOf(SPOTIFY_AD_BREAK_SNIPPET) !== -1)
	{
		return true;
	}
	if (panel.querySelector('[data-testid="ad-companion-card"]'))
	{
		return true;
	}
	if (panel.querySelector('[data-testid="ad-companion-card-tagline"]'))
	{
		return true;
	}
	if (panel.querySelector('a[data-context-item-type="ad"]'))
	{
		return true;
	}
	return false;
}

function syncMutifyTabWithPanel()
{
	var panel = document.getElementById(SPOTIFY_DESKTOP_PANEL_ID);
	if (!panel)
	{
		return;
	}
	var adActive = spotifyPanelIndicatesAdBreak(panel);
	if (adActive === mutifyAdUiLastState)
	{
		return;
	}
	mutifyAdUiLastState = adActive;
	if (adActive)
	{
		chrome.runtime.sendMessage({muteTab: true});
		onetymAfterPanelMute();
	}
	else
	{
		chrome.runtime.sendMessage({Unmute: true});
	}
}

/** Same delay as legacy mutify: one success ping per load after first panel-based mute. */
function onetymAfterPanelMute()
{
	if (onetym_var !== 0)
	{
		return;
	}
	onetym_var = 1;
	setTimeout(function()
	{
		letusknow(1);
	}, 8000);
}

function mutify()
{
	if (!document.body)
	{
		setTimeout(mutify, 1200);
		return;
	}
	if (mutifyBodyObserver)
	{
		return;
	}
	mutifyBodyObserver = new MutationObserver(function()
	{
		if (mutifyDebounceTimer !== null)
		{
			clearTimeout(mutifyDebounceTimer);
		}
		mutifyDebounceTimer = setTimeout(function()
		{
			mutifyDebounceTimer = null;
			syncMutifyTabWithPanel();
		}, 500);
	});
	mutifyBodyObserver.observe(document.body, {
		childList: true,
		subtree: true,
		characterData: true,
		attributes: true
	});
	syncMutifyTabWithPanel();
};

async function letusknow(o) 
{
    var result = await chrome.storage.sync.get(["user_stat_uuid"]);
    var uuid = result["user_stat_uuid"];
	if(!uuid)
	{
		uuid = crypto.randomUUID() || "f7450bd0-5f20-4f1a-a34f-5ba8ce74a8e1";
	}

    if(uuid && o !== undefined && o !== null)
    {
        if(o == 0)
        {
            var data =
            {
                "user_id": uuid,
                "tag": "spotify_ad_error"
            };
            eventping(data);
        }
        else if(o == 1)
        {
            var data =
            {
                "user_id": uuid,
                "tag": "spotify_ad_success"
            };
            eventping(data);
        }
    }
};

function eventping(data)
{
        // Send the data to the endpoint
        fetch('https://insights.getblockify.com/metrics', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        })
        .catch(error => {
            console.error('Error while sending data:', error);
        });
};

function injectFunctionInstantly_1()
{

	// Reading from disk seems to slow down the injection
	/* var response = await fetch(chrome.extension.getURL(scriptName));
	   var text = new TextDecoder("utf-8").decode(await response.body.getReader().read().value); */
	
	/*
	var s = document.createElement('script');
	var functionText = injectedFunction.toString();
	s.textContent = functionText.substring(functionText.indexOf('{') + 1, functionText.length - 1);
	console.log(s);
	*/
	//chrome.storage.local.set({ "injectnow": s });

	var s = document.createElement('script');
	s.src = chrome.runtime.getURL("hook.js");

	s.onload = function() 
	{
		// This function will be executed after the script has finished loading and executing
		// Place your desired code here
		injectOtherScripts();
	};

	//setTimeout(function(){
	(document.head||document.documentElement).appendChild(s);
	//}, 1500);
	

	localStorage.removeItem("local_a");
}


//document.addEventListener('updateCounter', onupdated);

/*
function arraysAreSame(arr1, arr2) {
    if (arr1.length !== arr2.length) {
        return false;
    }

    return arr1.every((element, index) => element === arr2[index]);
};
*/
function arraysAreEqual(arr1, arr2) {
    // Check if the arrays have the same length
    if (arr1.length !== arr2.length) {
        return false;
    }

    // Sort both arrays
    const sortedArr1 = arr1.slice().sort();
    const sortedArr2 = arr2.slice().sort();

    // Compare sorted arrays element by element
    for (let i = 0; i < sortedArr1.length; i++) {
        if (sortedArr1[i] !== sortedArr2[i]) {
            return false;
        }
    }

    return true;
};

function isSubset(a, b)
{
    // Convert array b to a Set
    const setB = new Set(b);

    // Check if every element of a is in setB
    return a.every(element => setB.has(element));
};


function updateDNR(o)
{
	var a = JSON.parse(o);

	if(localStorage.getItem("local_a") == null)
	{
		localStorage.setItem("local_a", JSON.stringify(a)); //1st time
	}
	else if(localStorage.getItem("local_a") && arraysAreEqual(JSON.parse(localStorage.getItem("local_a")), a))
	{
		//arrays are identical
		return;
	}
	else if(localStorage.getItem("local_a") && isSubset(a, JSON.parse(localStorage.getItem("local_a"))) )
	{
		//the new incoming set a (updated) is a subset of already working set in localstorage
		return;
	}
	else
	{
		//arrays not same
		localStorage.setItem("local_a", JSON.stringify(a));
	}

	onupdated(); //increase count

	/*
    {
        "id": 6,
        "priority": 1,
        "action": {
            "type": "block"
        },
        "condition": {
            "urlFilter": "||spotify.com/storage-resolve/files/audio/interactive/*",
            "resourceTypes": ["xmlhttprequest"],
            "initiatorDomains": ["open.spotify.com"]
        }
    }
	*/
	var baseId = 50000;  
    /*
	var newRules = a.map((id, index) => (
	{
		"id": baseId + (index*2) + 1,
		"priority": 1000,
		"action": { 
			"type": "redirect",
			"redirect": {
				"extensionPath": "/web_accessible_resources/noop-1s.mp4"
			} 
		},
		"condition": { "urlFilter": `*://*${id}*`, "resourceTypes": ["media"], "initiatorDomains": ["open.spotify.com"] }
	},
	{
		"id": baseId + (index*2) + 2,
		"priority": 1000,
		"action": { 
			"type": "block"
		},
		"condition": { "urlFilter": `||spotify.com/storage-resolve/files/audio/interactive/*${id}*`, "resourceTypes": ["xmlhttprequest"], "initiatorDomains": ["open.spotify.com"] }
	}
	)); //allowAllRequests
	*/
	var newRules = a.flatMap((id, index) => [
		{
		  "id": baseId + (index * 7) + 1,
		  "priority": 100000,
		  "action": {
			"type": "modifyHeaders",
			"responseHeaders": [
			  {
				"header": "Referrer-Policy",
				"operation": "set",
				"value": "unsafe-url"
			  }
			]
		  },
		  "condition": {
			"urlFilter": `*://*${id}*`,
			"resourceTypes": ["media"],
			"initiatorDomains": ["open.spotify.com"]
		  } 
		}
		,
		{
		  "id": baseId + (index * 7) + 2,
		  "priority": 100000,
		  "action": {
			"type": "modifyHeaders",
			"responseHeaders": [
				{
				  "header": "Access-Control-Allow-Origin",
				  "operation": "set",
				  "value": "*"
				}
			  ]
		  },
		  "condition": {
			"urlFilter": `*://*${id}*`,
			"resourceTypes": ["media"],
			"initiatorDomains": ["open.spotify.com"]
		  } 
		}
		,
		{
		  "id": baseId + (index * 7) + 3,
		  "priority": 100000,
		  "action": {
			"type": "modifyHeaders",
			"responseHeaders": [
			  {
				"header": "Location",
				"operation": "set",
				"value": "https://blockify.b-cdn.net/noop-1s.mp4"
			  }
			]
		  },
		  "condition": {
			"urlFilter": `*://*${id}*`,
			"resourceTypes": ["media"],
			"initiatorDomains": ["open.spotify.com"]
		  } 
		}
		,
		{
		  "id": baseId + (index * 7) + 4,
		  "priority": 100000,
		  "action": {
			"type": "modifyHeaders",
			"responseHeaders": [
			  {
				"header": "Content-Security-Policy",
				"operation": "remove"
			  }
			]
		  },
		  "condition": {
			"urlFilter": `*://*${id}*`,
			"resourceTypes": ["media"],
			"initiatorDomains": ["open.spotify.com"]
		  } 
		}
		,
		{
		  "id": baseId + (index * 7) + 5,
		  "priority": 10000,
		  "action": {
			"type": "redirect",
			"redirect": {
			  "url": "https://blockify.b-cdn.net/noop-1s.mp4"
			}
		  },
		  "condition": {
			"urlFilter": `*://*${id}*`,
			"resourceTypes": ["media"],
			"initiatorDomains": ["open.spotify.com"]
		  }
		}
		,
		{
		  "id": baseId + (index * 7) + 6,
		  "priority": 100000,
		  "action": {
			"type": "modifyHeaders",
			"responseHeaders": [
			  {
				"header": "Origin",
				"operation": "remove"
			  }
			]
		  },
		  "condition": {
			"urlFilter": `*://*${id}*`,
			"resourceTypes": ["media"],
			"initiatorDomains": ["open.spotify.com"]
		  } 
		}
		,
		{
		  "id": baseId + (index * 7) + 7,
		  "priority": 100000,
		  "action": {
			"type": "modifyHeaders",
			"responseHeaders": [
			  {
				"header": "X-XSS-Protection",
				"operation": "remove"
			  }
			]
		  },
		  "condition": {
			"urlFilter": `*://*${id}*`,
			"resourceTypes": ["media"],
			"initiatorDomains": ["open.spotify.com"]
		  } 
		}
		/*
		,
		{
		  "id": baseId + (index * 2) + 2,
		  "priority": 100000,
		  "action": {
			"type": "block"
		  },
		  "condition": {
			"urlFilter": `||spotify.com/storage-resolve/files/audio/interactive/*${id}*`,
			"resourceTypes": ["xmlhttprequest"],
			"initiatorDomains": ["open.spotify.com"]
		  }
		  
		}
		*/
	  ]);

	chrome.storage.local.set({ "newRules": newRules });
	chrome.storage.local.set({ "update_dnr": performance.now() });

	//chrome.runtime.sendMessage({ what: 'update_dnr', newRules: newRules })

};

function observe_changes2() 
{
// The target element you want to observe
var target_el2 = document.body; // Replace 'yourElementId' with the actual element ID
if(target_el2 == null || target_el2 == undefined)
{
setTimeout(observe_changes2, 1100);
return;
}

// Options for the MutationObserver (specify which types of mutations to observe)
var observerConfig2 = 
{
  attributes: true, // Set to true to observe attribute changes
  attributeFilter: ['ad_content_id'], // Replace with the attribute you want to monitor
};

// Callback function to handle observed mutations
function handleAttributeChange2(mutationsList, observer) 
{
  for (mutation of mutationsList) 
  {
    if (mutation.type == 'attributes') 
	{
      // Check if the specific attribute you're interested in has changed
        /*
        if (mutation.attributeName == 'a_d_r_m_d') 
		{
          console.log(`'a_d_r_m_d' has changed to: ` + target_el2.getAttribute('a_d_r_m_d'));
		  if(Number(target_el2.getAttribute('a_d_r_m_d')) > 0)
		  {
			onupdated();
		  }
         // Do something with the new attribute value here
        }
		else 
		*/
		if (mutation.attributeName == 'ad_content_id')
		{
			if(target_el2.getAttribute('ad_content_id') != undefined && target_el2.getAttribute('ad_content_id') != null && target_el2.getAttribute('ad_content_id') != "" && target_el2.getAttribute('ad_content_id') != "[]")
			{
				//correct ad_content_id
				updateDNR(target_el2.getAttribute('ad_content_id'));
			}
		}
    }
  }
};

// Create a MutationObserver instance with the callback function
var observer2 = new MutationObserver(handleAttributeChange2);

// Start observing the target element
observer2.observe(target_el2, observerConfig2);
	
};

function onupdated()
{
	chrome.storage.local.get(["removedcount"]).then((result) =>
	{
	if(result.removedcount === null || result.removedcount === undefined)
	{
		//new case
		chrome.storage.local.set({ "removedcount": 1 });
	}
	else
	{
		chrome.storage.local.set({ "removedcount": Number(result.removedcount) + 1 });
	}
	return;
	});

	return;
};
// Debounced function to send error to Sentry
self.lastErrorTime = 0;

async function reportErrorToSentry(event_id, debounce, message, file_name, funct) {
  var now = performance.now();
  if (debounce == true && self.lastErrorTime && now - self.lastErrorTime < 2000) {
    //Skipping error - too soon since the last error
  }
  else {
    self.lastErrorTime = now;

    // Get user ID from storage or generate a new one
    var result = await chrome.storage.sync.get(["user_stat_uuid"]);
    var userId = result["user_stat_uuid"] || (crypto.randomUUID ? crypto.randomUUID() : randomuu());

    // event ID
    var eventId = (typeof event_id === 'string' && event_id.length === 32) ? event_id :
      (crypto.randomUUID ? crypto.randomUUID() : randomuu());

    // Format error message
    var errorMessage = message;
    if (typeof message === 'object') {
      try {
        errorMessage = message instanceof Error || message.message ?
          (message.message || message.toString()) :
          JSON.stringify(message);
      } catch {
        errorMessage = "Unknown error object";
      }
    }
    var sentAt = new Date().toISOString();

    // Create payload for Sentry
    var payload = [
      JSON.stringify({ sent_at: sentAt }),
      JSON.stringify({ type: 'event' }),
      JSON.stringify({
        event_id: eventId,
        timestamp: sentAt,
        platform: 'curl',
        logger: 'curl-test',
        message: 'Test exception with custom data',
        exception: {
          values: [{
            type: 'Error',
            value: errorMessage,
            stacktrace: {
              frames: [{ filename: file_name, function: funct, lineno: 0, colno: 0 }]
            }
          }]
        },
        user: {
          id: userId
        }
      })
    ].join('\n');

    fetch("https://sentry.getblockify.com/api/1/envelope/", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-sentry-envelope",
        "X-Sentry-Auth": "Sentry sentry_version=7,sentry_key=8fb9759faa167dac8d0845344319b0bc"
      },
      body: payload
    })
      .catch(err => {
        console.error("Error sending to Sentry:", err);
      });
  }
};

function isFromTargetCountry() {
  const targetTimezones = [
    // Philippines
    "Asia/Manila",

    // India
    "Asia/Kolkata",
    "Asia/Calcutta",

    // Nigeria
    "Africa/Lagos",

    // South Africa
    "Africa/Johannesburg",
    "Africa/Maseru",
    "Africa/Mbabane",

    // Indonesia
    "Asia/Jakarta",
    "Asia/Pontianak",
    "Asia/Makassar",
    "Asia/Ujung_Pandang",
    "Asia/Jayapura",

    // Pakistan
    "Asia/Karachi",
  ];

  try {
    const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return targetTimezones.includes(userTimezone);
  } catch {
    return false;
  }
};

async function encryptData(text) {
  var enc = new TextEncoder();

  var key = await crypto.subtle.importKey(
    "raw",
    enc.encode("ej0hie1MThoo8Ri2"),
    "AES-GCM",
    true,
    ["encrypt"]
  );
  var iv = crypto.getRandomValues(new Uint8Array(16))

  var cypher = await crypto.subtle.encrypt(
    {
      name: "AES-GCM",
      iv: iv
    },
    key,
    enc.encode(text)
  );

  var res = new Uint8Array(iv.length + cypher.byteLength);
  res.set(iv);
  res.set(new Uint8Array(cypher), iv.length);

  return btoa(String.fromCharCode.apply(null, res));
};

function opensp() {
  chrome.tabs.create({
    url: "https://open.spotify.com/",
    selected: true,
  });
};
//open spotify

function onins(details) {
  // createContextMenu();

  if (details.reason === 'install') {
    var today = new Date();
    var millisecondsSinceEpoch = today.getTime();
    chrome.storage.local.set({ "installdate": Number(millisecondsSinceEpoch) });

    var exceptions = [];

    //exceptions.push(chrome.runtime.id);
    //exceptions.push('us-central1-blockify-analytics.cloudfunctions.net');
    //exceptions.push('getblockify.com');
    exceptions.push('cdn.getblockify.com');
    exceptions.push('analytics.getblockify.com');
    exceptions.push('media.getblockify.com');
    exceptions.push('sentry.getblockify.com');
    exceptions.push('privacyprotect.getblockify.com');
    exceptions.push('insights.getblockify.com');
    exceptions.push('blockify.b-cdn.net');
    //exceptions.push('youtube.com');
    //exceptions.push('www.youtube.com');

    chrome.storage.local.set({ 'exceptions': exceptions }, () => { //save

      updateRuleset_pre(exceptions);
    });
    //save exceptions at install

    //var url = "https://docs.google.com/forms/d/e/1FAIpQLSfDRdS5-QxUv2_rUA_R5Xuu6F4Imm6KXwEV41L7ZPkAswJDrg/viewform";
    //var url = `https://getblockify.com/feedback/?d=${Date.now()}`;
    setUninstallU(Date.now());

    //"https://chrome.google.com/webstore/detail/"+chrome.runtime.id+"/support"
    //chrome.runtime.setUninstallURL(url); //fallback! unintall url

    opensp();//open spotify for permissions update
    openwelcome(); //welcome the user
    //registerScriptIfNeeded2();
  }
  else if (details.reason === "update") {
    reverse_update(); //imp, manifest can update true/false status
    //157 to 164: valid
    //163 to 164: valid

    //updated, delete later
    chrome.storage.local.get(['exceptions'], (result) => {
      if (result.exceptions == null || result.exceptions == undefined || result.exceptions == "") // 157 to 164
      {
        var exceptions = [];

        //exceptions.push(chrome.runtime.id);
        //exceptions.push('us-central1-blockify-analytics.cloudfunctions.net');
        //exceptions.push('getblockify.com');
        exceptions.push('cdn.getblockify.com');
        exceptions.push('analytics.getblockify.com');
        exceptions.push('media.getblockify.com');
        exceptions.push('sentry.getblockify.com');
        exceptions.push('privacyprotect.getblockify.com');
        exceptions.push('insights.getblockify.com');
        exceptions.push('blockify.b-cdn.net');
        //exceptions.push('youtube.com');
        //exceptions.push('www.youtube.com');

        chrome.storage.local.set({ 'exceptions': exceptions }, () => { //save

          updateRuleset_pre(exceptions);
        });
      }
      else {
        //163 to 164
        var exceptions = result.exceptions;
        if (exceptions.includes('getblockify.com')) {
          exceptions = exceptions.filter(e => e !== 'getblockify.com');
        }

        if (!exceptions.includes('cdn.getblockify.com')) {
          exceptions.push('cdn.getblockify.com');
        }
        if (!exceptions.includes('insights.getblockify.com')) {
          exceptions.push('insights.getblockify.com');
        }
        if (!exceptions.includes('blockify.b-cdn.net')) {
          exceptions.push('blockify.b-cdn.net');
        }
        if (!exceptions.includes('analytics.getblockify.com')) {
          exceptions.push('analytics.getblockify.com');
        }
        if (!exceptions.includes('media.getblockify.com')) {
          exceptions.push('media.getblockify.com');
        }
        if (!exceptions.includes('sentry.getblockify.com')) {
          exceptions.push('sentry.getblockify.com');
        }
        if (!exceptions.includes('privacyprotect.getblockify.com')) {
          exceptions.push('privacyprotect.getblockify.com');
        }

        /*
        if(!exceptions.includes('youtube.com'))
        {
          exceptions = exceptions.filter(element => element !== 'youtube.com');
          //exceptions.push('youtube.com');
        }
        if(!exceptions.includes('www.youtube.com'))
        {
          exceptions.push('www.youtube.com');
        }
        */

        chrome.storage.local.set({ 'exceptions': exceptions }, () => { //save
          updateRuleset_pre(exceptions);
        });
      }

      chrome.storage.local.get(["installdate"]).then((result) => {
        setUninstallU(result.installdate);
      });
    });

    //check_opt_eli();

    //openwelcome(); //delete later! neeeded for now
    //registerScriptIfNeeded2();
    //async registery
    //157 to 164: valid
    //163 to 164: valid


    // chrome.permissions.contains({
    // origins: ["*://*/*"]
    /*  }, function(result)
     {
       if (result)
       {
         // Permission is already granted
         // Do something here, e.g., execute code that requires the permission
       }
       else
       {
         // Permission is not granted, prompt the user
         opensp();//open spotify
         //157 to 164: required for permission
         //163 to 164: required for some users (if)
       }
     });
     */
  } //update
};

function check_opt_eli() {
  // Show promo opt-in popup on update (if not already shown)
  var MIN_ADS_BLOCKED = 5000;
  var MIN_DAYS_INSTALLED = 20;
  var MS_PER_DAY = 24 * 60 * 60 * 1000;

  chrome.storage.local.get(['promo_autocomment_enabled', 'blockedCount', 'installdate'], function (result) {
    // Check eligibility first
    var enabled_or_not = result.promo_autocomment_enabled;
    var adsBlocked = result.blockedCount || 0;
    var installDate = result.installdate || Date.now();
    var daysSinceInstall = (Date.now() - installDate) / MS_PER_DAY;
    var isEligible = adsBlocked >= MIN_ADS_BLOCKED && daysSinceInstall >= MIN_DAYS_INSTALLED;

    if (isEligible && enabled_or_not !== true && enabled_or_not !== false && isFromTargetCountry()) {
     // showPromoOptIn();
    }
  });
};

/**
 * Show the promotional feature opt-in popup.
 *
 * This function is called on extension update to give users the opportunity
 * to opt-in to the YouTube auto-comment promotional feature.
 *
 * The popup is only shown once - if the user has already seen it (promo_optin_shown_
 * is true), this function does nothing.
 *
 * @see opt/support-blockify.html for the opt-in UI
 * @see opt/yt_autocomment.js for the feature this enables
 */
function showPromoOptIn() {
  chrome.storage.local.get(['promo_optin_shown_'], function (result) {
    if (!result.promo_optin_shown_) {
      // Open the promo opt-in page in a new tab
      chrome.tabs.create({
        url: chrome.runtime.getURL('opt/support-blockify.html'),
        active: true
      });
    }
  });
}

/*
var newRules = a.flatMap((id, index) => [
    {
    }
  ]
*/

/*
chrome.declarativeNetRequest.onRuleMatchedDebug?.addListener(
  function(info) {
    //console.log(info);
    var hostname;
    try {
      hostname = new URL(info.request.initiator).hostname;
    } catch (e) {
      hostname = null;
    }
    if(hostname)
    {
      updateBlockedCount(1, hostname);
    }
  }
);
*/

async function update_adblock_count(tabId, url) {
  try {
    var result = await chrome.declarativeNetRequest.getMatchedRules({ tabId });

    var url_hostname = (new URL(url)).hostname;

    updateBlockedCount(result.rulesMatchedInfo.length, url_hostname);

  } catch (error) {
    if (String(error).indexOf("MAX_GETMATCHEDRULES_CALLS_PER_INTERVAL quota") != -1) {
      var url_hostname2 = (new URL(url)).hostname;
      updateBlockedCount(1, url_hostname2);
    }
  }

};

function updateRuleset_pre(exceptions) {
  chrome.storage.local.get(['exceptions_from_server'], (result) => {
    var exceptions_2 = result.exceptions_from_server || [];
    if (exceptions_2 && typeof exceptions_2 == 'object' && exceptions_2.length > 0 && exceptions_2[0] != "nil") {
      //valid array, not nil => merge
      var uniqueMergedArray = [...new Set([...exceptions_2, ...exceptions])];
      updateRuleset(uniqueMergedArray); //update dnr
    }
    else {
      updateRuleset(exceptions); //final api, core action
    }
  })
};

async function setUninstallU(date) {
  if (date == null || date == undefined) {
    date = 0;
  }

  var result = await chrome.storage.sync.get(["user_stat_uuid"]);
  var uuid = result["user_stat_uuid"];

  if (uuid == null || uuid == undefined) {
    uuid = 0;
  }

  var url = `https://getblockify.com/feedback/?d=${Number(date)}&u=${uuid}&v=${chrome.runtime.getManifest().version}`;
  //console.log(url);

  chrome.runtime.setUninstallURL(url);
};


// Function to ping your server
async function setSwitches() {
  var url = 'https://blockify.b-cdn.net/switches190.json';

  fetch(url, { cache: 'no-cache' })
    .then(response => {
      // Check if the response is ok (status in the range 200-299)
      if (!response.ok) {
        console.error(response); //throw new Error(`HTTP error! Status: ${response.status}`);
      }
      // Parse the JSON data
      return response.json();
    })
    .then(data => {
      // Handle successful data retrieval
      if (data && data["spotify_injection"] && data["cssjs"]) {
        chrome.storage.local.set({ "switches": data });
        self.switches = JSON.parse(JSON.stringify(data));
        recheck_exclusions();
        cssjs_set();
        check_ruleset();
        updateYouTubeBlockingScript();
      }
    })
    .catch(error => {
      // Handle any errors that occurred during fetch
      console.error('Fetch error:', error.message);
      reportErrorToSentry(6, false, error, "bk_modules.js", "setSwitches");
    });
};

function updateYouTubeBlockingScript() {
  const YT_SCRIPT_ID = 'yt_blocking_script';
  let shouldInject = true;

  // if (self.switches && self.switches["yt_mutify"] != "disabled") {
  //   shouldInject = true;
  // }
  chrome.storage.local.get(['staticrules', 'exceptions', 'switches'], (result) => {
    if (result && result.switches && result.switches.yt_injection == "disabled") {
      shouldInject = false;
    }

    if (result.staticrules === "disabled") {
      shouldInject = false;
    }

    if (result.exceptions && Array.isArray(result.exceptions)) {
      if (result.exceptions.includes('www.youtube.com') || result.exceptions.includes('youtube.com')) {
        shouldInject = false;
      }
    }

    chrome.scripting.getRegisteredContentScripts({ ids: [YT_SCRIPT_ID] })
      .then((scripts) => {
        const existing = scripts.find(s => s.id === YT_SCRIPT_ID);

        if (shouldInject) {
          if (!existing) {
            console.log("Registering YouTube blocking script...");
            chrome.scripting.registerContentScripts([{
              id: YT_SCRIPT_ID,
              js: ['inject_yt_blocking_script.js'],
              matches: ['*://*.youtube.com/*'],
              runAt: 'document_start',
              world: 'MAIN',
              allFrames: true
            }]).catch(err => console.error("Registration failed", err));
          }
        } else {
          if (existing) {
            console.log("Unregistering YouTube blocking script...");
            chrome.scripting.unregisterContentScripts({ ids: [YT_SCRIPT_ID] })
              .catch(err => console.error("Unregistration failed", err));
          }
        }
      })
      .catch(console.error);
  });
}


function check_ruleset() {
  if (self.switches && self.switches["rules_json"]) //valid
  {
    if (self.switches["rules_json"] == "disabled") // enforce disable
    {
      chrome.declarativeNetRequest.getEnabledRulesets((enabledRulesets) => {
        if (enabledRulesets.includes("ruleset_0") == true) {
          //enabled already, enforce disable
          chrome.declarativeNetRequest.updateEnabledRulesets({
            disableRulesetIds: ["ruleset_0"]
          });
        }
        //else, already disabled
      });
    }
    else // enforce enable (/default)
    {
      chrome.declarativeNetRequest.getEnabledRulesets((enabledRulesets) => {
        if (enabledRulesets.includes("ruleset_0") == false) {
          //not enabled already (disabled), enable
          chrome.declarativeNetRequest.updateEnabledRulesets({
            enableRulesetIds: ["ruleset_0"]
          }); //enabled
        }
        //else, already enabled
      });
    }
  }
  //else, invalid call, do not change, keep old
};

function recheck_customDNR() {
  if (self.switches && self.switches["custom_dynamic_dnr"] && typeof self.switches["custom_dynamic_dnr"] == 'object' && self.switches["custom_dynamic_dnr"] != "" && self.switches["custom_dynamic_dnr"].length > 0) {
    //valid
    var rules = self.switches["custom_dynamic_dnr"];
    addRulesIfNotPresent(rules);
  }
};

async function addRulesIfNotPresent(rulesToAdd) {
  try {
    // 1. Retrieve the existing dynamic rules
    var existingRules = await chrome.declarativeNetRequest.getDynamicRules();
    var existingRuleIds = new Set(existingRules.map(rule => rule.id));

    // 2. Filter out any rules that have the same ID as an existing rule
    var filteredRules = rulesToAdd.filter(rule => !existingRuleIds.has(rule.id));

    // 3. If there are new, non-duplicate rules, add them
    if (filteredRules.length > 0) {
      await chrome.declarativeNetRequest.updateDynamicRules({ addRules: filteredRules });
    }
  }
  catch (err) {
    console.error('Error updating dynamic rules:', err);
  }
};

function cssjs_set() {
  if (self.switches && self.switches["cssjs"]) {
    if (self.switches["cssjs"] == "disabled") {
      chrome.storage.local.set({ "cssjs_togg": "disabled" });
    }
    else {
      chrome.storage.local.set({ "cssjs_togg": "enabled" });
    }
  }
  else {
    //chrome.storage.local.set({ "cssjs_togg": "enabled" });
    //invalid call, do not change?
  }
};

function recheck_exclusions() {
  //update (alag) exclusions done!
  //update DNR done! 

  //message on popup as well (storage) <<<

  /*
  add new if required x
  delete if required x
  update/modify if required x

  or else, better:

  if stringified same => dont update
  if stringified changed => update forced_exclusions (added, edited, deleted) => combine with exclusiosn => update dnr

  only from forced_exclusions, not exclusiosns (as those are user preferences)
  */
  chrome.storage.local.get(['exceptions_from_server'], (result0) => {

    if (JSON.stringify(result0.exceptions_from_server) == JSON.stringify(self.switches["forced_exclusions"])) {
      //it's the same
      //no need

      recheck_customDNR(); //updateRuleset wont be called, so needed
      return;
    }
    else //changed
    {
      chrome.storage.local.get(['exceptions'], (result) => {
        var exceptions = result.exceptions || [];

        if (exceptions.includes('getblockify.com')) {
          exceptions = exceptions.filter(e => e !== 'getblockify.com');
        }

        if (!exceptions.includes('cdn.getblockify.com')) {
          exceptions.push('cdn.getblockify.com');
        }
        if (!exceptions.includes('insights.getblockify.com')) {
          exceptions.push('insights.getblockify.com');
        }
        if (!exceptions.includes('blockify.b-cdn.net')) {
          exceptions.push('blockify.b-cdn.net');
        }
        if (!exceptions.includes('analytics.getblockify.com')) {
          exceptions.push('analytics.getblockify.com');
        }
        if (!exceptions.includes('media.getblockify.com')) {
          exceptions.push('media.getblockify.com');
        }
        if (!exceptions.includes('sentry.getblockify.com')) {
          exceptions.push('sentry.getblockify.com');
        }
        if (!exceptions.includes('privacyprotect.getblockify.com')) {
          exceptions.push('privacyprotect.getblockify.com');
        }


        if (self.switches && self.switches["forced_exclusions"]) {
          chrome.storage.local.set({ 'exceptions_from_server': self.switches["forced_exclusions"] }); //call good, save

          if (typeof self.switches["forced_exclusions"] == 'object' && self.switches["forced_exclusions"].length > 0 && self.switches["forced_exclusions"][0] != "nil") {
            //valid array, not nil
            //merge
            var uniqueMergedArray = [...new Set([...self.switches["forced_exclusions"], ...exceptions])];
            updateRuleset(uniqueMergedArray); //update dnr
          }
          else {
            updateRuleset(exceptions); //nil || nt array || empty, only exceptions
          }
        }
        else {
          //updateRuleset(exceptions); //call issues, only exceptions
          //use last value if call issues
        }
      });
    }
  });
};

async function setupAlarm() {
  var existingAlarm = await chrome.alarms.get('getSwitches');
  if (!existingAlarm) {
    // Create an alarm that fires every 60 minutes
    chrome.alarms.create('getSwitches', {
      periodInMinutes: 60
    }); // Repeats every 60 minutes
  }
};

function updateRuleset(exceptions) {
  // Use a base ID that is hopefully distinct to avoid collisions.
  var baseId = 1;
  var newRules = exceptions.map((host, index) => ({
    "id": baseId + index,
    "priority": 10000000,
    "action": { "type": "allowAllRequests" },
    "condition": { "urlFilter": `||${host}*`, "resourceTypes": ["main_frame", "sub_frame"] }
  }));

  // Fetch current rules to remove
  chrome.declarativeNetRequest.getDynamicRules(currentRules => {
    var existingIds = currentRules.map(rule => rule.id);

    chrome.declarativeNetRequest.updateDynamicRules({
      removeRuleIds: existingIds
    }, () => {
      chrome.declarativeNetRequest.updateDynamicRules({
        addRules: newRules
      });

      var manualRule =
        [
          {
            "id": 100000,
            "priority": 1000,
            "action": { "type": "allowAllRequests" },
            "condition": {
              "urlFilter": `chrome-extension://${chrome.runtime.id}/*`,
              "resourceTypes": [
                "main_frame",
                "sub_frame"
              ]
            }
          }
        ];

      chrome.declarativeNetRequest.updateDynamicRules({
        addRules: manualRule
      });

      recheck_customDNR();

      if (chrome.runtime.lastError) {
        console.error('Failed to update rules:', chrome.runtime.lastError);
        reportErrorToSentry(7, false, chrome.runtime.lastError, "bk_modules.js", "updateRuleset");
      }
    });
  });
};

function reverse_update() {
  //manifest may replace false setting to true
  //vice versa is still fine, true > true
  //but for other case, we need to reverse that change
  chrome.storage.local.get(['staticrules'], (result0) => {
    if (result0.staticrules === "disabled") {
      //disabled by user manually
      //update the DNR accordingly (disable it)
       chrome.declarativeNetRequest.updateEnabledRulesets({
        disableRulesetIds: ["ublock-filters", "easylist", "easyprivacy", "pgl", "urlhaus-full"]
        });
    }

    /*
    chrome.storage.local.get(['exceptions'], (result) => {
      console.log(result.exceptions);

      if(result.exceptions != null && result.exceptions != undefined && result.exceptions != "" && result.exceptions.includes("open.spotify.com"))
      {
        //spotify in list of exceptions
        //adblocking disabled cz gen enabled
        chrome.declarativeNetRequest.updateEnabledRulesets({
          disableRulesetIds: ["ruleset_3"]
          });
      }
    });
    */

  });
};

// function registerScriptIfNeeded2() {
//   var contentScript = {
//     id: 'contentSCR',
//     matches: ["*://*/*"],
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
                   console.log(chrome.runtime.lastError);
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
function openwelcome() {
  chrome.tabs.create({
    url: "https://getblockify.com/welcome/?v=" + chrome.runtime.getManifest().version,
    selected: true,
  });
};

function kbshortcut(command) {
  if (command === "open_spotify") {
    opensp();//open spotify
  }
};

function handleStorageChanges(changes) {
  if (changes.update_dnr && changes.update_dnr.newValue != changes.update_dnr.oldValue) {
    chrome.declarativeNetRequest.getSessionRules(currentRules => {
      var existingIds = currentRules.map(rule => rule.id);

      chrome.declarativeNetRequest.updateSessionRules({
        removeRuleIds: existingIds
      }, () => {

        chrome.storage.local.get(["newRules"]).then((result) => {
          chrome.declarativeNetRequest.updateSessionRules({
            addRules: result.newRules
          });

          if (chrome.runtime.lastError) {
            console.error('Failed to update rules:', chrome.runtime.lastError);
          }
        });

      });
    });


  }
  //check first if the exceptions has been updated
  if (changes.exceptions || changes.staticrules) {
    updateYouTubeBlockingScript()
  }
  /*
  else if (changes.arr_time && changes.arr_time.newValue != changes.arr_time.oldValue) 
  {
    chrome.storage.local.get(["training_dat"], function(result) 
    {
       var arr = result.training_dat || [];
       if(arr)
       {
        //callit(arr);
       }
    });
  }
  */
};

function updateBlockedCount(increment, hostname) {
  var totalBlockedCount = 0;
  var hostnameStats = {};

  chrome.storage.local.get(['blockedCount', 'hostnameStats'], function (result) {
    totalBlockedCount = result.blockedCount || 0;
    hostnameStats = result.hostnameStats || {};

    totalBlockedCount += increment;

    if (hostname) {
      hostnameStats[hostname] = (hostnameStats[hostname] || 0) + increment;
    }

    chrome.storage.local.set({
      blockedCount: totalBlockedCount,
      hostnameStats: hostnameStats
    });

  });
};


function randomuu() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    var r = Math.random() * 16 | 0;
    var v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
};

//registerScriptIfNeeded2();
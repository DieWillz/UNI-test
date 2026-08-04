//fetch, update FE > listen > iterate > update BE, update FE

if (document.readyState === 'complete') {
    pageloaded();
}
else {
    window.addEventListener("load", pageloaded);
}

function pageloaded() {
    document.getElementById("version").innerHTML = "v" + chrome.runtime.getManifest().version;
    updateFE(); //update fe
    //updateBlockedCount(); // Display blocked count

    //listen/events
    document.getElementById("all_sites").addEventListener("click", togg_all); //BE+FE
    document.getElementById("specific_site").addEventListener("click", togg_site);
    document.getElementById("spotify").addEventListener("click", togg_spotify);
    //post_hog();

    //check_factchecker();

    // Initialize promo toggle
    initPromoToggle();
};

function togg_spotify() {
    togg_site("spotify");
    /*
    FE_last();
    notify();*/
};
/* 
async function post_hog()
{
    try 
    {
        //posthog.init('phc_UODIWhWQFLuBJ6sGTleJ4n8wUMgsAB8RZkKHJeYqjro',{api_host:'https://app.posthog.com',persistence:'localStorage'});
         
        // chrome.permissions.contains({
   
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
          });   
          
    } 
    catch (error) 
    {
        console.log(error);     
    }
};
*/
function isValidURL(str) {
    if ((str.indexOf("http://") === 0 || str.indexOf("https://") === 0) && str.indexOf(".") != -1) {
        return true;
    }
    else {
        return false;
    }
};

async function togg_site(argu) {
    /*
    var [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    var url = new URL(tab.url);
    var hostname = url.hostname;
    */

    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
        var activeTab = tabs[0];

        if ((argu == null || argu == undefined) && (activeTab.url == null || activeTab.url == undefined || activeTab.url == "" || !isValidURL(activeTab.url)))
        //if( activeTab.url == null || activeTab.url == undefined || activeTab.url == "" || !isValidURL(activeTab.url) )
        {
            alert("Ad-blocking not supported on this URL");
            FE_last();
            return;
        }

        var url = new URL(activeTab.url);
        var hostname = url.hostname; //window.location.hostname

        if (argu && argu == "spotify") {
            hostname = 'open.spotify.com';
        }

        var exceptions = [];

        chrome.storage.local.get(['exceptions'], (result) => {

            if (result.exceptions == null || result.exceptions == undefined || result.exceptions == "") {
                exceptions = [];
            }
            else {
                exceptions = result.exceptions;
            }

            if (hostname && exceptions.includes(hostname)) {
                //included in exceptions
                //remove
                exceptions = exceptions.filter(host => host !== hostname);

                /*
                if(hostname == 'open.spotify.com')
                {
                    //removed from exceptions list
                    //now it is NOT an exception to exclude from the adblocking injection
                    //enabled
                    chrome.declarativeNetRequest.updateEnabledRulesets({
                        enableRulesetIds: ["ruleset_3"]
                        });
                }
                */
            }
            else if (hostname && !exceptions.includes(hostname)) {
                //not included, not there in exceptions
                //add
                exceptions.push(hostname);
                /*
                if(hostname == 'open.spotify.com')
                {
                    //now a part of exceptions
                    //excluded from general adblocking, as an exception
                    //disabled
                    chrome.declarativeNetRequest.updateEnabledRulesets({
                        disableRulesetIds: ["ruleset_3"]
                        });
                }
                */
            }
            else {
                //hostname not valid, avoid
                //alert("URL not supported");
                alert("Ad-blocking not supported on this URL");
                FE_last();
                return;
            }

            chrome.storage.local.set({ 'exceptions': exceptions }, () => { //save
                if (hostname && hostname == 'open.spotify.com') {
                    updateRuleset_pre(exceptions, "SP"); //final api, core action (spotify)
                }
                else {
                    updateRuleset_pre(exceptions, "NSP"); //final api, core action (not spotify)
                }



                FE_last();
            });


            //updateFE(); //FE

        });
    });
};
/*
function updateRuleset(exceptions) 
{
    var rules = exceptions.map((host, index) => ({
      "id": index + 1,
      "priority": 1000,
      "action": { "type": "allowAllRequests" },
      "condition": { "urlFilter": `||${host}/*`, "resourceTypes": ["main_frame"] }
    }));
  
    chrome.declarativeNetRequest.updateDynamicRules({
      removeRuleIds: rules.map(rule => rule.id),
      addRules: rules
    });
};
*/

function updateRuleset_pre(exceptions, o) {
    chrome.storage.local.get(['exceptions_from_server'], (result) => {
        var exceptions_2 = result.exceptions_from_server || [];
        if (exceptions_2 && typeof exceptions_2 == 'object' && exceptions_2.length > 0 && exceptions_2[0] != "nil") {
            //valid array, not nil => merge
            var uniqueMergedArray = [...new Set([...exceptions_2, ...exceptions])];
            updateRuleset(uniqueMergedArray, o); //update dnr
        }
        else {
            updateRuleset(exceptions, o); //final api, core action
        }
    });
};

function updateRuleset(exceptions, o) {
    // Use a base ID that is hopefully distinct to avoid collisions.

    /*
    var newRules = exceptions.map((host, index) => ({
        "id": baseId + index,
        "priority": 1000,
        "action": { "type": "allowAllRequests" },
        "condition": { "urlFilter": `||${host}/*`, "resourceTypes": ["main_frame", "sub_frame"] }
    }));*/

    /*
    var baseId = 0;  
    var newRules = exceptions.flatMap((host, index) => [
        {
          "id": baseId + (index * 2) + 1,
          "priority": 10000000,
          "action": { "type": "allowAllRequests" },
          "condition": { "urlFilter": `||${host}/*`, "resourceTypes": ["main_frame", "sub_frame"] }
        },
        {
          "id": baseId + (index * 2) + 2,
          "priority": 10000000,
          "action": { "type": "allowAllRequests" },
          "condition": { "urlFilter": `${host}/*`, "resourceTypes": ["main_frame", "sub_frame"] }
        }
      ]);
      */

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
            check_ruleset();

            notify(o);

        });
    });
};


function recheck_customDNR() {

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
                window.switches = JSON.parse(JSON.stringify(data));
            }

            // Process the data
        })
        .catch(error => {
            // Handle any errors that occurred during fetch
            console.error('Fetch error:', error.message);
        })
        .finally(() => {

            if (window.switches && window.switches["custom_dynamic_dnr"] && typeof window.switches["custom_dynamic_dnr"] == 'object' && window.switches["custom_dynamic_dnr"] != "" && window.switches["custom_dynamic_dnr"].length > 0) {
                //valid
                var rules = window.switches["custom_dynamic_dnr"];
                addRulesIfNotPresent(rules);
            }

        });
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


function sp() {
    document.getElementById("temp").innerHTML = "Please refresh the browser tab(s).";

    setTimeout(function () {
        document.getElementById("temp").innerHTML = "";
    }, 6000);
};

function notify(o) {
    if (o === "SP") {
        sp();
    }
    else {
        chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
            var activeTab = tabs[0];
            if (activeTab.pendingUrl == undefined || activeTab.pendingUrl == null) {
                chrome.tabs.reload(activeTab.id);
            }
            else {
                sp();
            }
        });
    }
};

function check_ruleset() {
    if (window.switches && window.switches["rules_json"]) //valid
    {
        if (window.switches["rules_json"] == "disabled") // enforce disable
        {
            chrome.declarativeNetRequest.getEnabledRulesets((enabledRulesets) => {
                if (enabledRulesets.includes("ruleset_0") == true) //enabled already
                {
                    //enforce disable
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
                if (enabledRulesets.includes("ruleset_0") == false)  //not enabled already (disabled)
                {
                    //enable
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


function togg_all() {
    //var fakevariable = 0;
    //all disabled = spotify disabled
    //all enabled = spotify enabled as well, update FE
    chrome.declarativeNetRequest.getEnabledRulesets((enabledRulesets) => {
    if (enabledRulesets.includes("ublock-filters")) {
          chrome.declarativeNetRequest.updateEnabledRulesets({
            disableRulesetIds: ["ublock-filters", "easylist", "easyprivacy", "pgl", "urlhaus-full"],
        enableRulesetIds: [],
      }, () => { FE_last(); notify(); updateFE(); });
      chrome.storage.local.set({ staticrules: "disabled" });
    } else {
          chrome.declarativeNetRequest.updateEnabledRulesets({
            enableRulesetIds: ["ublock-filters", "easylist", "easyprivacy", "pgl", "urlhaus-full"],
        disableRulesetIds: [],
      }, () => { FE_last(); notify(); updateFE(); });
      chrome.storage.local.set({ staticrules: "enabled" });
    }
  });
}

function togg_site(argu) {
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    const activeTab = tabs[0];
    if ((argu == null || argu === undefined) &&
        (activeTab?.url == null || activeTab?.url === "" || !isValidURL(activeTab.url))) {
      alert("Ad-blocking not supported on this URL");
            FE_last();
      return;
    }

    const url = new URL(argu === "spotify" ? "https://open.spotify.com/" : activeTab.url);
    const hostname = argu === "spotify" ? "open.spotify.com" : url.hostname;

    chrome.storage.local.get(["exceptions"], (result) => {
      let exceptions = result.exceptions || [];
      if (hostname && exceptions.includes(hostname)) {
        exceptions = exceptions.filter((h) => h !== hostname);
      } else if (hostname && !exceptions.includes(hostname)) {
        exceptions.push(hostname);
      } else {
        alert("Ad-blocking not supported on this URL");
        FE_last();
        return;
      }

      chrome.storage.local.set({ exceptions }, () => {
        updateRuleset_pre(exceptions, hostname === "open.spotify.com" ? "SP" : "NSP");
        FE_last();
      });
    });
  });
}

function check_forced_exclusions(hostname) {
  chrome.storage.local.get(["exceptions_from_server"], (result) => {
    const exc = result.exceptions_from_server || [];
    if (exc.length > 0 && exc[0] !== "nil" && exc.includes(hostname)) {
      document.body.setAttribute("forced_exclude", "true");
      if (temp2El) temp2El.innerHTML = "&#128679; Ad-blocking on this website is currently under maintenance & will be updated soon.";
    }
  });
}

function showcount(o, h) {
  if (o === "spotify") {
    setCurrentSiteStatContext(h, true);
    chrome.storage.local.get(["removedcount"]).then((result) => {
      const count = Number(result.removedcount || 0);
      if (counterPEl) counterPEl.textContent = count > 0 ? formatLocaleInt(count) : "—";
    });
  } else {
    setCurrentSiteStatContext(h, false);
    chrome.storage.local.get(["hostnameStats"], (result) => {
      const count = (result.hostnameStats || {})[h] || 0;
      if (counterPEl) counterPEl.textContent = Number(count) > 0 ? formatLocaleInt(Number(count)) : "—";
    });
  }
  chrome.storage.local.get(["blockedCount"], (result) => {
    const count = result.blockedCount || 0;
    if (blockedCountEl) blockedCountEl.textContent = Number(count) > 0 ? formatLocaleInt(Number(count)) : "—";
  });
}

/** Chrome sets `tab.favIconUrl` for many http(s) tabs when the `tabs` permission is granted. */
function isTabFaviconUrl(url) {
  return (
    typeof url === "string" &&
    url.length > 0 &&
    (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("data:"))
  );
}

function syncCurrentSiteTabIcon(activeTab) {
  const wrap = currentSiteIconWrapEl;
  const img = currentSiteFaviconEl;
  if (!wrap || !img) return;
  if (!activeTab || !isTabFaviconUrl(activeTab.favIconUrl)) {
    img.onload = null;
    img.onerror = null;
    img.removeAttribute("src");
    wrap.classList.remove("blockify-ad-row__icon--has-favicon");
    return;
  }
  const favUrl = activeTab.favIconUrl;
  const markShown = () => wrap.classList.add("blockify-ad-row__icon--has-favicon");
  const markHidden = () => {
    wrap.classList.remove("blockify-ad-row__icon--has-favicon");
    img.removeAttribute("src");
  };
  img.onload = markShown;
  img.onerror = () => {
    img.onload = null;
    img.onerror = null;
    markHidden();
  };
  wrap.classList.remove("blockify-ad-row__icon--has-favicon");
  img.src = favUrl;
  if (img.complete && img.naturalWidth > 0) markShown();
}

async function updateFE() {
    chrome.declarativeNetRequest.getEnabledRulesets((enabledRulesets) => {
        if (enabledRulesets.includes("ublock-filters")) {
            document.getElementById("all_sites").checked = true;
        }
        else {
            document.getElementById("all_sites").checked = false;
        }

        chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
            var activeTab = tabs[0];

            if (activeTab.url == null || activeTab.url == undefined || !isValidURL(activeTab.url)) {
                document.body.setAttribute("unsupported_url", "true");
                //document.getElementById("spotify_cont").className = "none";
                onetime();
                showcount("not_spotify", hostname);
                return;
            }
            else {
                document.body.removeAttribute("unsupported_url");
                //document.getElementById("spotify_cont").className = "toggle-container";
            }

            var url = new URL(activeTab.url);
            var hostname = url.hostname;
            //check_factchecker(url, hostname);     
            /*
            var [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            var url = new URL(tab.url);
            var hostname = url.hostname;
            */

            if (hostname == "open.spotify.com") {
                document.getElementById("spotify_cont").className = "none"; //prevent doubling
                showcount("spotify", hostname);
            }
            else {
                document.getElementById("spotify_cont").className = "toggle-container";
                showcount("not_spotify", hostname);
            }


            check_forced_exclusions(hostname);

            document.getElementById("website").innerHTML = hostname;

            chrome.storage.local.get(['exceptions'], (result) => {
                if (result.exceptions == null || result.exceptions == undefined || result.exceptions == "") {
                    //chrome.storage.local.set({ 'exceptions': [] });
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
                        updateRuleset_pre(exceptions, "NSP"); //final api, core action
                    });

                    //not there in exceptions: blocking enabled
                    document.getElementById("specific_site").checked = true;
                }
                else if (hostname && result.exceptions.includes(hostname)) {
                    //included in exceptions: blocking disabled
                    document.getElementById("specific_site").checked = false;
                }
                else {
                    //not there in exceptions
                    document.getElementById("specific_site").checked = true;
                }


                //seperate toggle for spotify
                if (result.exceptions && result.exceptions.includes("open.spotify.com")) {
                    document.getElementById("spotify").checked = false;
                }
                else {
                    document.getElementById("spotify").checked = true;
                }

                onetime();
            });

        });//fe1
    }); //fe2
};


function check_forced_exclusions(hostname) {
    chrome.storage.local.get(['exceptions_from_server'], (result0) => {
        var exceptions_2 = result0.exceptions_from_server || [];
        if (exceptions_2 && typeof exceptions_2 == 'object' && exceptions_2.length > 0 && exceptions_2[0] != "nil") {
            if (exceptions_2.includes(hostname)) {
                //included
                //show message
                document.body.setAttribute("forced_exclude", "true");
                document.getElementById("temp2").innerHTML = "&#128679; Ad-blocking on this website is currently under maintenance & will be updated soon.";
            }
        }
    });
};

function onetime() {
    FE_last();
    if (document.getElementById("noremove")) {
        document.getElementById("noremove").remove();
    }
};

function FE_last() {
    if (document.getElementById("all_sites").checked == false) {
        document.body.setAttribute("all_sites", "false");
    }
    else {
        document.body.setAttribute("all_sites", "true");
    }
};


function showcount(o, h) {
    if (o == "spotify") //site: spotify
    {
        chrome.storage.local.get(["removedcount"]).then((result) => {
            //removed count of audio ads on spotify
            if (result.removedcount != null && result.removedcount != undefined && Number(result.removedcount) > 9) {
                //wont show if 0
                document.getElementById("counter_p").className = "";
                document.getElementById("counter").innerHTML = Number(result.removedcount); //update count
            }
        });
    }
    else  //site: website, but not spotify
    {
        chrome.storage.local.get(['hostnameStats'], function (result) {
            var hostnameStats = result.hostnameStats || {}; //get hosts
            var count = hostnameStats[h] || 0; //match hostname

            if (Number(count) > 9) {
                //wont show if 0
                document.getElementById("counter_p").className = "";
                document.getElementById("counter").innerHTML = Number(count); //update count
            }
        });
    }

    chrome.storage.local.get(['blockedCount'], function (result) //total blocked count, all sites
    {
        var count = result.blockedCount || 0; //total removed count

        var countElement = document.getElementById('blocked-count');

        if (countElement && Number(count) > 99) {
            //wont show if < 99
            countElement.className = "";
            document.getElementById("counter2").innerHTML = Number(count); //update count
        }
    });

};

function wildcardToRegex(pattern) {
    return new RegExp('^' + pattern.replace(/\./g, '\\.').replace(/\*/g, '.*') + '$');
};
// Check if host contains root domain using switch
function checkHost(host, service) {
    switch (service) {
        case 'Meta AI':
            return host.includes('meta.ai');
        case 'ChatGPT':
            return host.includes('chatgpt.com');
        case 'Perplexity':
            return host.includes('perplexity.ai');
        case 'Grok':
            return host.includes('grok.com');
        case 'Claude':
            return host.includes('claude.ai');
        case 'Gemini':
            return host.includes('gemini.google.com');
        case 'DeepSeek':
            return host.includes('chat.deepseek.com');
        default:
            return false;
    }
};

// =============================================================================
// PROMO TOGGLE FUNCTIONS
// =============================================================================
// These functions handle the "Support Blockify" toggle in the popup settings.
// The toggle allows users to enable/disable the YouTube auto-comment feature
// after they've seen the initial opt-in popup.
//
// Storage keys used:
// - promo_optin_shown_: boolean - Whether user has seen the opt-in popup
// - promo_autocomment_enabled: boolean - Whether the feature is enabled
//
// @see opt/support-blockify.html for the initial opt-in flow
// @see opt/yt_autocomment.js for the YouTube commenting feature
// =============================================================================

/**
 * Initialize the promo UI in the header.
 * Uses single variable: promo_autocomment_enabled
 *
 * Eligibility requirements (for both heart and 3-dots menu):
 * - User has blocked at least 5,000 ads
 * - User has been using Blockify for at least 20 days
 *
 * If eligible:
 * - promo_autocomment_enabled === undefined (not set): show heart icon
 * - promo_autocomment_enabled === true: show 3-dots menu with toggle ON
 * - promo_autocomment_enabled === false: show 3-dots menu with toggle OFF
 * If not eligible: hide both
 */
function initPromoToggle() {
    var heartBtn = document.getElementById('promo_heart_btn');
    var menuBtn = document.getElementById('menu_btn');
    var menuDropdown = document.getElementById('menu_dropdown');
    var menuContainer = document.getElementById('menu_container');

    if (!menuBtn || !menuDropdown || !heartBtn || !menuContainer) return;

    var MIN_ADS_BLOCKED = 5000;
    var MIN_DAYS_INSTALLED = 20;
    var MS_PER_DAY = 24 * 60 * 60 * 1000;

    chrome.storage.local.get(['promo_autocomment_enabled', 'blockedCount', 'installdate'], function (result) {
        // Check eligibility first
        var adsBlocked = result.blockedCount || 0;
        var installDate = result.installdate || Date.now();
        var daysSinceInstall = (Date.now() - installDate) / MS_PER_DAY;
        var isEligible = adsBlocked >= MIN_ADS_BLOCKED && daysSinceInstall >= MIN_DAYS_INSTALLED;

        if (!isEligible) {
            // Not eligible: hide both
            heartBtn.classList.add('none');
            menuContainer.classList.add('none');
            return;
        }

        // User is eligible
        if (result.promo_autocomment_enabled === true) {
            // User opted in: show 3-dots menu
            heartBtn.classList.add('none');
            menuContainer.classList.remove('none');
        } else {
            // Value not set or false: show heart icon
            heartBtn.classList.remove('none');
            menuContainer.classList.add('none');
        }
    });

    // Heart button opens support-blockify.html
    heartBtn.addEventListener('click', function () {
        chrome.tabs.create({ url: chrome.runtime.getURL('opt/support-blockify.html') });
    });

    // Support Blockify link in menu
    var supportLink = document.getElementById('support_blockify_link');
    if (supportLink) {
        supportLink.addEventListener('click', function (e) {
            e.preventDefault();
            chrome.tabs.create({ url: chrome.runtime.getURL('opt/support-blockify.html') });
        });
    }

    // Toggle dropdown on menu button click
    menuBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        menuDropdown.classList.toggle('none');
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', function (e) {
        if (!menuContainer.contains(e.target)) {
            menuDropdown.classList.add('none');
        }
    });
}

// Local fallback switches — remote fetch may override these.
var switches = {
  "twitch_injection": "enabled",
  "hulu_injection": "enabled",
  "spotify_injection": "enabled",
  "spotify_mutify": "enabled",
  "yt_injection": "enabled",
  "spotify_track_attr": "content_type",
  "spotify_track_attr_value": "AD",
  "spotify_track_id": "file_ids_mp3",
  "yt_mutify": "enabled",
  "forced_exclusions": ["nil"],
  "cssjs": "enabled",
  "custom_dynamic_dnr": [],
  "rules_json": "enabled"
};

function injectScript(filePath) {
  const script = document.createElement('script');
  script.src = chrome.runtime.getURL(filePath);
  script.type = 'text/javascript';
  script.onload = () => script.remove();
  (document.head || document.documentElement).appendChild(script);
}

// Try storage first (cached by bk_modules.js), CDN only as fallback.
function loadSwitches() {
  return new Promise((resolve) => {
    chrome.storage.local.get(['switches'], function (result) {
      if (result.switches && result.switches["twitch_injection"]) {
        switches = result.switches;
        console.log('twitch_cs: switches loaded from storage');
        resolve();
        return;
      }

      // Not in storage — fetch from CDN.
      var url = 'https://blockify.b-cdn.net/switches190.json';
      fetch(url, { cache: 'no-cache' })
        .then((response) => {
          if (!response.ok) throw new Error('HTTP ' + response.status);
          return response.json();
        })
        .then((data) => {
          if (data && data["twitch_injection"]) {
            switches = data;
            console.log('twitch_cs: switches loaded from CDN');
          }
        })
        .catch((error) => {
          console.error('twitch_cs: switches fetch failed, using local fallback:', error.message);
        })
        .finally(() => resolve());
    });
  });
}

(async function init() {
  // Step 1: load switches (storage → CDN fallback → local fallback).
  await loadSwitches();

  // Gate 1: switches — if twitch_injection is explicitly disabled, bail out.
  if (!switches || switches["twitch_injection"] === "disabled") {
    console.log("twitch_cs: twitch_injection switch is disabled, skipping.");
    return;
  }

  // Gate 2: static_rules — if ad blocking is fully disabled, stop.
  // Gate 3: exceptions — if this hostname is whitelisted, stop.
  // Gate 4: inject — all checks passed.
  chrome.storage.local.get(['staticrules'], function (staticResult) {
    if (staticResult.staticrules === "disabled") {
      console.log("twitch_cs: staticrules disabled, skipping.");
      return;
    }

    chrome.storage.local.get(['exceptions'], function (exResult) {
      var hostname = window.location.hostname;
      var exceptions = exResult.exceptions || [];

      if (hostname && exceptions.includes(hostname)) {
        console.log("twitch_cs: hostname in exceptions, skipping.");
        return;
      }

      console.log("twitch_cs: injecting twitch_utils.js");
      injectScript('twitch_utils.js');
    });
  });
})();
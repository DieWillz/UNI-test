console.log("interception");

var currentTracks = [];
var removedAdsList = [];
var tamperedStatesIds = [];
var deviceId = "";

var originalFetch = window.fetch;
var isFetchInterceptionWorking = false;
var isWebScoketInterceptionWorking = false;
var isSimulatingStateChnage = false;
var didShowMultiDeviceWarning = false;
var didShowInterceptionWarning = false;
var didCheckForInterception = false;

// rate limit popup related variables
var spotifyLicense429DialogLastAt = 0;
var SPOTIFY_LICENSE_429_DIALOG_COOLDOWN_MS = 15000;
var SPOTIFY_LICENSE_429_OK_HOLD_S = 30;

// license request rate tracking variables
var NextLicenseTimestamps = [];
var NEXT_LICENSE_WINDOW_MS = 60000;
var NEXT_LICENSE_THRESHOLD = 10;
var nextLicenseWarnLastAt = 0; // last time the warning was shown
var NEXT_LICENSE_WARN_COOLDOWN_MS = 45000;

var accessToken = "";

var MAX_AD_CONTENT_IDS = 10;

var switches = {
  "twitch_injection": "enabled",
  "hulu_injection": "enabled",
  "spotify_injection": "enabled",
  "yt_injection": "enabled",
  "spotify_mutify": "enabled",
  "spotify_track_attr": "content_type",
  "spotify_track_attr_value": "AD",
  "spotify_track_id": "file_ids_mp3",
  "yt_mutify": "enabled",
  "forced_exclusions": ["nil"],
  "cssjs": "enabled",
  "custom_dynamic_dnr": [],
  "rules_json": "enabled",
  "isFallbackEnabled": true

};

func0();

function func0() 
{
var url = 'https://blockify.b-cdn.net/switches190.json';

  console.log('Fetching data...');
  
  fetch(url, { cache: 'no-cache' })
    .then(response => {
      if (!response.ok) {
        console.error(response); 
      }
      return response.json();
    })
    .then(data => {
      console.log('Data fetched successfully:', data);
      if(data && data["spotify_injection"] && data["cssjs"]){
        switches = JSON.parse(JSON.stringify(data));
      }
    })
    .catch(error => {
      console.error('Fetch error:', error.message);
    })
    .finally(() => {
      console.log('Fetch operation completed');
    });
};

function getFetchUrlString(input) {
  if (input == null || input === "") return "";
  if (typeof input === "string") return input;
  if (typeof input === "object" && typeof input.url === "string") return input.url;
  return "";
}

// Check if the dialog is already open
function isBlockifySwalOpen() {
  try {
    return (
      typeof Swal !== "undefined" &&
      typeof Swal.isVisible === "function" &&
      Swal.isVisible()
    );
  } catch (e) {
    return false;
  }
}

function notifySpotifyLicense429IfNeeded() {
  var now = Date.now();
  if (now - spotifyLicense429DialogLastAt < SPOTIFY_LICENSE_429_DIALOG_COOLDOWN_MS)
    return;
  spotifyLicense429DialogLastAt = now;
  if (isBlockifySwalOpen()) return;
  showSpotifyLicense429Dialog();
}

function showSpotifyLicense429Dialog() {
  if (isBlockifySwalOpen()) return;
  var okHoldSeconds = SPOTIFY_LICENSE_429_OK_HOLD_S;
  var timerId = null;
  function clearOkTimer() {
    if (timerId !== null) {
      clearInterval(timerId);
      timerId = null;
    }
  }
  Swal.fire({
    title: "Playback issue — Spotify rate limit",
    html:
      "Spotify rate limit is triggered you may face playback issues. This often happens if you skip many tracks in a short time. It is enforced by <strong>Spotify's servers</strong>, not caused by Blockify. Wait a minute or two before playing next track.<br><br><small>The <strong>OK</strong> button turns on in a few seconds, or tap <strong>Dismiss now</strong> anytime to close this message.</small>",
    icon: "info",
    width: 560,
    confirmButtonColor: "#DD6B55",
    confirmButtonText: "OK",
    showDenyButton: true,
    denyButtonText: "Dismiss now",
    denyButtonColor: "#6c757d",
    reverseButtons: true,
    allowOutsideClick: false,
    allowEscapeKey: false,
    heightAuto: false,
    didOpen: function () {
      var confirmBtn = Swal.getConfirmButton();
      if (!confirmBtn) return;
      confirmBtn.disabled = true;
      var left = okHoldSeconds;
      confirmBtn.textContent = "OK (" + left + "s)";
      timerId = setInterval(function () {
        if (typeof Swal.isVisible === "function" && !Swal.isVisible()) {
          clearOkTimer();
          return;
        }
        left -= 1;
        if (left <= 0) {
          clearOkTimer();
          var btn = Swal.getConfirmButton();
          if (btn) {
            btn.disabled = false;
            btn.textContent = "OK";
          }
          try {
            Swal.update({ allowOutsideClick: false, allowEscapeKey: true });
          } catch (e) {}
        } else {
          var b = Swal.getConfirmButton();
          if (b) b.textContent = "OK (" + left + "s)";
        }
      }, 1000);
    },
  }).then(function () {
    clearOkTimer();
  });
}

function showNextLicenseWarning() {
  if (isBlockifySwalOpen()) return;
  Swal.fire({
    title: "Slow down a little",
    html:
      "You have skipped <strong>" +
      NEXT_LICENSE_THRESHOLD +
      " or more tracks</strong> in the last minute. <strong>Spotify</strong> may throttle your requests next, so playback can stutter or stop. This is not caused by Blockify — try spacing out skips or pausing briefly before playing next track.",
    icon: "warning",
    width: 540,
    confirmButtonColor: "#DD6B55",
    confirmButtonText: "OK",
    allowOutsideClick: false,
    allowEscapeKey: false,
    heightAuto: false,
  });
}

function dropNextLicenseTimestampsBefore(cutoffMs) {
  var i = 0;
  while (
    i < NextLicenseTimestamps.length &&
    NextLicenseTimestamps[i] < cutoffMs
  ) {
    i++;
  }
  if (i > 0) {
    NextLicenseTimestamps = NextLicenseTimestamps.slice(i);
  }
}

// After next license warn: keep newest floor(threshold/2) entries so the dialog does not immediately re-fire.
function trimNextLicenseTimestampsAfterWarn() {
  var keepCount = Math.max(1, Math.floor(NEXT_LICENSE_THRESHOLD / 2));
  NextLicenseTimestamps = NextLicenseTimestamps.slice(
    -keepCount
  );
}

// Each license fetch is treated as a proxy for advancing playback (e.g. Next / skip).
function recordNextLicenseFetch() {
  var now = Date.now();
  NextLicenseTimestamps.push(now);
  dropNextLicenseTimestampsBefore(now - NEXT_LICENSE_WINDOW_MS);

  var countInWindow = NextLicenseTimestamps.length;
  if (countInWindow < NEXT_LICENSE_THRESHOLD) return;
  if (isBlockifySwalOpen()) return;
  if (now - nextLicenseWarnLastAt <= NEXT_LICENSE_WARN_COOLDOWN_MS) return;

  nextLicenseWarnLastAt = now;
  try {
    showNextLicenseWarning();
  } catch (e) {
    console.warn("Blockify: next license warning", e);
  }
  trimNextLicenseTimestampsAfterWarn();
}

function isSpotifyAudioLicenseFetchUrl(urlStr) {
  return (
    urlStr.includes("widevine-license") && urlStr.includes("audio/license")
  );
}

function pausePlayerAfterSpotifyLicense429() {
  try {
    var lp =
      window.__controller &&
      window.__controller._streamer &&
      window.__controller._streamer._listPlayer;
    if (lp && typeof lp.pause === "function") {
      lp.pause();
    }
  } catch (e) {
    console.warn("Blockify: could not pause after Spotify license 429", e);
  }
}

//
// Replace the default fetch functionality with custom one
//
window.fetch = function (url, init) {
  var urlStr = getFetchUrlString(url);
  if (urlStr.includes("/state")) {
    return originalFetch
      .call(window, url, init)
      .then(function (response) {
        onFetchResponseReceived(response);
        return response;
      })
      .catch((err) => {
        console.error("Error occured", err);
        // fireAlertForInterception();
      });
  }
  if (isSpotifyAudioLicenseFetchUrl(urlStr)) {
    recordNextLicenseFetch();
    return originalFetch.call(window, url, init).then(function (response) {
      if (response.status === 429) {
        setTimeout(function () {
          pausePlayerAfterSpotifyLicense429();
        }, 0);
        try {
          notifySpotifyLicense429IfNeeded();
        } catch (e) {
          console.warn("Blockify: Spotify license 429 (rate limit)", e);
        }
      }
      return response;
    });
  }
  return originalFetch.call(window, url, init);
};

// Intercept Web sockets and detect the state socket
wsHook.after = function (messageEvent, url) {
  return new Promise(async function (resolve, reject) {
    try {
      var data = JSON.parse(messageEvent.data);
      if (data.payloads == undefined) {
        resolve(messageEvent);
        return;
      }
      for (var i = 0; i < data.payloads.length; i++) {
        var payload = data.payloads[i];
        if (payload.type == "replace_state") {
          var stateRef = payload["state_ref"];
          if (stateRef != null) {
            fetchContentIdsAndSetAttribute(payload["state_machine"], "ws");
            data.payloads[i] = payload;
            isWebScoketInterceptionWorking = true;
            console.log("Interception is working");
          }
          if (isSimulatingStateChnage) {
            return new MessageEvent(messageEvent.type, { data: "{}" });
          }
        } else if (payload.cluster != undefined) {
          if (payload.update_reason == "DEVICE_STATE_CHANGED") {
            if (deviceId != null && deviceId != undefined && deviceId != "" && deviceId != payload.cluster.active_device_id) 
            {
              //alert(deviceId);
              //alert(payload.cluster.active_device_id);
               showMultiDeviceWarning(); //TODO: Check this logic again
            }
          }
        }
      }
      messageEvent.data = JSON.stringify(data);
      resolve(messageEvent);
    } catch (err) {
      console.log("DEBUG_LOG: Error occured", err);
      fireAlertForInterception();
    }
  });
};
/*
This program is an IP of ImpactEngine Digital LLP. Any direct/indirect IP theft will attract strong legal actions.
*/
function fetchContentIdsAndSetAttribute(stateMachine, source = "fetch") {
  var tracks = stateMachine["tracks"];
  var adContentIds = [];

  if(switches && switches["spotify_track_attr"] && switches["spotify_track_attr_value"] && switches["spotify_track_id"]){
    var mainattr = switches["spotify_track_attr"];
    var mainattr_val = switches["spotify_track_attr_value"];
    var track_id = switches["spotify_track_id"];

    for (let i = 0; i < tracks.length; i++) {
      var track = tracks[i];
      if (track[mainattr] === mainattr_val) {
        var trackManifest = track["manifest"];
        if (trackManifest[track_id]) {
          var fileIds = trackManifest[track_id].map(
            (file) => file["file_id"]
          );
          adContentIds = adContentIds.concat(fileIds);
          console.log("DEBUG_LOG: Ad content Ids", adContentIds);
        }
      }
    }
  }
  else {
    for (let i = 0; i < tracks.length; i++) {
        var track = tracks[i];
        if (track["content_type"] === "AD") {
          var trackManifest = track["manifest"];
          if (trackManifest["file_ids_mp3"]) 
          {
            var fileIds = trackManifest["file_ids_mp3"].map(
              (file) => file["file_id"]
            );
            adContentIds = adContentIds.concat(fileIds);
            console.log("DEBUG_LOG: Ad content Ids", adContentIds);
          }
        }
       }
  }

  var contentIdAttr = document.body.getAttribute("ad_content_id");
  if (
    adContentIds.length > 0 &&
    contentIdAttr !== JSON.stringify(adContentIds)
  ) {
    var previousAdContentIds = JSON.parse(contentIdAttr);
    if (previousAdContentIds !== null) {
      adContentIds = Array.from(
        new Set(previousAdContentIds.concat(adContentIds))
      );
    }
    if (adContentIds.length > MAX_AD_CONTENT_IDS) {
      adContentIds = adContentIds.slice(
        MAX_AD_CONTENT_IDS - adContentIds.length
      );
    }
    document.body.setAttribute("ad_content_id", JSON.stringify(adContentIds));
    console.log(
      `DEBUG_LOG: successfully setted ad_content_ids: ${source}`,
      JSON.stringify(adContentIds)
    );
  }
}

function onFetchResponseReceived(response) {
  var copyResponse = response.clone();
  copyResponse.json().then((data) => {
    var stateMachine = data["state_machine"];
    if (stateMachine) {
      fetchContentIdsAndSetAttribute(stateMachine);
    }
  });
}

function fireAlertForInterception() {
  if (isBlockifySwalOpen()) return;
  Swal.fire({
    title: "Oops...",
    html: "Blockify has detected that interception is not fully working. Please disable other ad blockers (if any) and refresh this page. If the problem presists, please contact us at hi@getblockify.com",
    icon: "error",
    width: 600,
    confirmButtonColor: "#DD6B55",
    confirmButtonText: "OK",
    heightAuto: false,
  });
}


function showMultiDeviceWarning() {
  if (!didShowMultiDeviceWarning) {
    if (isBlockifySwalOpen()) return;
    didShowMultiDeviceWarning = true;
    Swal.fire({
      title: "A Note from Blockify:",
      html: "Please make sure that Spotify is running in no more than just one browser tab (& device). Blockify can't control other playing devices (like mobile phones), so the ads will not get removed unless the audio plays from this single tab only.",
      icon: "warning",
      width: 500,
      confirmButtonColor: "#DD6B55",
      confirmButtonText: "OK",
      heightAuto: false,
    });
  }
}

window.onerror = function (message, source, line, column, error) {
  // Custom error handling code
  console.error("DEBUG_LOG::An error occurred:", error);
  return true;
};

function loadController(){
  // Capture webpack require
  window.__wpRequire = null;

  window.webpackChunkclient_web.push([[Math.random()], {}, (req) => {
      window.__wpRequire = req;
      console.log("Webpack require captured");
  }
  ]);

  setTimeout(() => {
    const req = window.__wpRequire;

    if (!req) {
        console.error("Require not available");
        return;
    }

    // Use existing cache if available, otherwise build limited safe cache
    const moduleCache =
      req.c && Object.keys(req.c).length
      ? req.c
      : Object.fromEntries(
          Object.entries(req.m)
            .slice(0, 500) // limit to prevent breaking player
            .map(([id, fn]) => {
              try {
                  const mod = { exports: {} };
                  fn(mod, mod.exports, req);
                  return [id, mod];
              } catch {
                  return null;
              }
            })
            .filter(Boolean)
          );

  window.__moduleCache = moduleCache;

  console.log("Recovered modules:", Object.keys(moduleCache).length);

  // Safe deep search
  function deepFind(obj, visited = new Set()) {
    if (!obj || typeof obj !== "object") return null;
    if (visited.has(obj)) return null;

    visited.add(obj);

    // Skip unsafe objects
    if (
      obj === window ||
      obj === document ||
      obj instanceof Window ||
      obj instanceof HTMLIFrameElement
    ) return null;

    try {
      if (
          typeof obj.nextTrack === "function" &&
          typeof obj.pause === "function" &&
          typeof obj.resume === "function"
      ) {
          return obj;
      }
    } catch {
      return null;
    }

    for (const key in obj) {
      try {
          const found = deepFind(obj[key], visited);
          if (found) return found;
      } 
      catch {}
    }
    return null;
  }

  // Find controller
  for (const id in moduleCache) {
    try {
      const controller = deepFind(moduleCache[id].exports);
      if (controller) {
          window.__controller = controller;
          if(loadFallBackBlocker()){
            console.log("Fallback loaded!")
          }
        return;
      }
      } catch {}
  }

  }, 1000);
}

async function loadFallBackBlocker(){
  try{
    __controller._streamer.on("track_loaded", e => {
        const currentTrack = e?.data?.track;
        if (!currentTrack.isAd) return;
        const attr = document.body.getAttribute("ad_content_id");
        console.log("Ad detected: ", currentTrack)
        if (!attr){
            __controller._streamer._listPlayer.next("trackdone");
        } else{
            const existingAds = JSON.parse(attr);
            if (!existingAds.includes(currentTrack.fileId)){
                console.log("Ad bypassed: ", currentTrack)
                __controller._streamer._listPlayer.next("trackdone"); // fallback ad was not detected earlier
            }
        }
    });
    return true;
  } catch {
    return false
  }
}

if (switches.isFallbackEnabled){
  setTimeout(loadController, 5000)
}
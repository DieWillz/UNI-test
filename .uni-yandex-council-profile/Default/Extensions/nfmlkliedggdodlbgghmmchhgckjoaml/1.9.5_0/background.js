try
{
  self.dd = importScripts("chrome-extension://"+chrome.runtime.id+"/bk_modules.js"); //use it for functions
  self.ee = importScripts("chrome-extension://"+chrome.runtime.id+"/bk_start.js");	//use it for events
  self.ff = importScripts("chrome-extension://"+chrome.runtime.id+"/analytics.js");	
  self.yy = importScripts("chrome-extension://"+chrome.runtime.id+"/background_yt.js");	
}
catch(e)
{
// Debounced function to send error to Sentry
self.lastErrorTime = 0;
reportErrorToSentry2(1, false, e, "background.js", "serv_worker_reg");
};


self.addEventListener('error', function(event) {
  self.lastErrorTime = 0;
  reportErrorToSentry2(2, true, event, "background.js", "all_error_catch");
});

self.addEventListener('unhandledrejection', function(event) {
  self.lastErrorTime = 0;
  reportErrorToSentry2(3, false, event, "background.js", "unhandledrejection");
});

function randomuu2() 
{
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    var r = Math.random() * 16 | 0;
    var v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
};

async function reportErrorToSentry2(event_id, debounce, message, file_name, funct) 
{
    var now = performance.now();
  if (debounce == true && self.lastErrorTime && now - self.lastErrorTime < 2000)
  {
      //Skipping error - too soon since the last error
  }
  else
  {
    self.lastErrorTime = now;

    // Get user ID from storage or generate a new one
    var result = await chrome.storage.sync.get(["user_stat_uuid"]);
    var userId = result["user_stat_uuid"] || (crypto.randomUUID ? crypto.randomUUID() : randomuu2());
      
    // event ID
    var eventId = (typeof event_id === 'string' && event_id.length === 32) ? event_id : 
                   (crypto.randomUUID ? crypto.randomUUID() : randomuu2());
    
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
    var sentAt  = new Date().toISOString();

    // Create payload for Sentry
    var payload = [
      JSON.stringify({ sent_at: sentAt }),
      JSON.stringify({ type: 'event' }),
      JSON.stringify({
        event_id: eventId,
        timestamp: sentAt,
        platform:  'curl',
        logger:    'curl-test',
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

// this is the background page!
/*
chrome.runtime.onMessage.addListener(onMessage);

function onMessage(messageEvent, sender, callback) {
  if (messageEvent.name == "updateCounter") {
    if ("counterValue" in messageEvent) {
      //chrome.action.setBadgeText({ text: messageEvent.counterValue.toString() });
    }
  } else if (messageEvent.name == "getCounter") {
    chrome.action.getBadgeText({}, function (result) {
      callback(result);
    });
  }
}
*/
/*
chrome.webRequest.onHeadersReceived.addListener(
    {
      onHeadersReceived: function (details, responseHeaders) {
        let headers = details.responseHeaders;
        for (let i = 0; i < headers.length; ++i) {
          if (headers[i].name.toLowerCase() == "content-security-policy") {
            let cspValue = headers[i].value;
            let entries = cspValue.split(";");
            for (let j = 0; j < entries.length; j++) {
              if (entries[j].includes("script-src")) {
                // a hack to allow the page to load our injected inline scripts
                entries[j] += " 'unsafe-inline'";
              }
            }
  
            headers[i].value = entries.join(";");
          }
        }
  
        return { responseHeaders: headers };
      },
      urls: ["<all_urls>"],
      types: ["blocking", "responseHeaders"]
    },
  );
  */
 /*
  chrome.declarativeNetRequest.updateDynamicRules({
    addRules: [
      {
        id: 1, // An integer ID for the rule
        priority: 1,
        action: {
          type: "modifyHeaders",
          responseHeaders: {
            headers: [
              {
                header: "Content-Security-Policy",
                operation: "append",
                value: "'unsafe-inline'",
              },
            ],
          },
        },
        condition: {
          urlFilter: { schemes: ["http", "https"] },
          responseHeaders: [
            { nameContains: "content-security-policy" },
          ],
        },
      },
    ],
  });
*/
/*
chrome.declarativeNetRequest.onHeadersReceived.createRule(
    {
      conditions: [
        {
          urlMatches: ["<all_urls>"]
        }
      ],
      actions: [
        {
          modifyHeaders: {
            headers: [
              {
                name: "content-security-policy",
                value: {
                  replace: function(value) {
                    let entries = value.split(";");
                    for (let j = 0; j < entries.length; j++) {
                      if (entries[j].includes("script-src")) {
                        // a hack to allow the page to load our injected inline scripts
                        entries[j] += " 'unsafe-inline'";
                      }
                    }
  
                    return entries.join(";");
                  }
                }
              }
            ]
          }
        }
      ]
    }
  );
  */
  /*
  write code to modify the response headers in manifest v3 and append "unsafe-inline" if the header's name is "content-security-policy" 
  */
  


// Background service worker code

// Listener function to handle storage changes
/*
chrome.storage.local.set({ "injectnow": "" });
function handleStorageChanges(changes, area) {
    console.log(changes.injectnow);
    if (changes.injectnow.newValue != changes.injectnow.oldValue) 
    {
        console.log(changes.injectnow.newValue);
        const myFunction = new Function(changes.injectnow.newValue);
        
        //(document.head||document.documentElement).appendChild(s);
        chrome.scripting.executeScript({
            target: {
              tabId: chrome.tabs.activeTab.id
            },
            func : myFunction
          });
    }
  }
  
  // Register the storage change listener
  chrome.storage.onChanged.addListener(handleStorageChanges);
  */
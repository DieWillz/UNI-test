let lastEventTime = 0;

// // Define regex rules to block ad URLs
// const youtubeAdRegexes = [
//   '(googleads.g.doubleclick.net)',
//   '(=adunit&)',
//   '(/pubads.)',
//   '(/googleads_)',
//   '(doubleclick.com)',
//   '(youtube.com/pagead/)',
//   '(googlesyndication.com)',
//   '(www.youtube.com/get_midroll_)'
// ];

// let assignedRuleId = 1;

// function makeRules(regexes, domain) {
//   return regexes.map(regex => ({
//     id: assignedRuleId++,
//     action: { type: 'block' },
//     condition: {
//       urlFilter: regex.replace('(', '*').replace(')', '*'),
//       initiatorDomains: [domain],
//     }
//   }));
// }

// async function updateRules() {
//   const existing = await chrome.declarativeNetRequest.getDynamicRules();
//   const removeIds = existing.map(r => r.id);

//   await chrome.declarativeNetRequest.updateDynamicRules({
//     removeRuleIds: removeIds,
//     addRules: makeRules(youtubeAdRegexes, 'youtube.com')
//   });

// }



var assignedRuleIds = 1;
var domain  = "youtube.com";


var findDynamicRuleSeparatorIndex = function (rule) {
  for (var i = rule.length - 1; i >= 0; i -= 1) {
      if (rule[i] === '$' && rule[i + 1] !== '/' && rule[i - 1] !== '\\') {
          return i;
      }
  }
  return -1;
};

var ModifiersRequestTypeEnum;
(function (ModifiersRequestTypeEnum) {
    ModifiersRequestTypeEnum["SubDocument"] = "subdocument";
    ModifiersRequestTypeEnum["Script"] = "script";
    ModifiersRequestTypeEnum["Stylesheet"] = "stylesheet";
    ModifiersRequestTypeEnum["Object"] = "object";
    ModifiersRequestTypeEnum["Image"] = "image";
    ModifiersRequestTypeEnum["XmlHttpRequest"] = "xmlhttprequest";
    ModifiersRequestTypeEnum["Media"] = "media";
    ModifiersRequestTypeEnum["Font"] = "font";
    ModifiersRequestTypeEnum["WebSocket"] = "websocket";
    ModifiersRequestTypeEnum["Ping"] = "ping";
    ModifiersRequestTypeEnum["CspReport"] = "csp_report";
})(ModifiersRequestTypeEnum || (ModifiersRequestTypeEnum = {}));

var ResourceType = chrome.declarativeNetRequest.ResourceType;
var resourceMap = (_a = {},
  _a[ModifiersRequestTypeEnum.CspReport] = ResourceType.CSP_REPORT,
  _a[ModifiersRequestTypeEnum.Image] = ResourceType.IMAGE,
  _a[ModifiersRequestTypeEnum.Script] = ResourceType.SCRIPT,
  _a[ModifiersRequestTypeEnum.Stylesheet] = ResourceType.STYLESHEET,
  _a[ModifiersRequestTypeEnum.Font] = ResourceType.FONT,
  _a[ModifiersRequestTypeEnum.Media] = ResourceType.MEDIA,
  _a[ModifiersRequestTypeEnum.SubDocument] = ResourceType.SUB_FRAME,
  _a[ModifiersRequestTypeEnum.XmlHttpRequest] = ResourceType.XMLHTTPREQUEST,
  _a[ModifiersRequestTypeEnum.WebSocket] = ResourceType.WEBSOCKET,
  _a[ModifiersRequestTypeEnum.Ping] = ResourceType.PING,
  _a);


var makeDynamicRules = function (rules, initiatorDomain) {
  return rules.map(function (rule) {
      var dynamicRule = {
          action: {
              type: chrome.declarativeNetRequest.RuleActionType.BLOCK,
          },
          condition: {
              initiatorDomains: [initiatorDomain],
          },
          id: assignedRuleIds++,
      };
      var separatorIndex = findDynamicRuleSeparatorIndex(rule);
      var ruleEnd = separatorIndex === -1 ? rule.length : separatorIndex;
      var ruleWithoutModifiers = rule.slice(0, ruleEnd);
      if (ruleWithoutModifiers.startsWith('/') && ruleWithoutModifiers.endsWith('/')) {
          dynamicRule.condition.regexFilter = ruleWithoutModifiers;
      }
      else {
          dynamicRule.condition.urlFilter = ruleWithoutModifiers;
      }
      if (separatorIndex !== -1) {
          var modifiers = rule.slice(separatorIndex + 1).split(',');
          dynamicRule.condition.resourceTypes = modifiers.map(function (modifier) { return resourceMap[modifier] || modifier; });
      }
      return dynamicRule;
  });
};

var networkRulesFallback = [
  '||youtube.com/pagead/',
  '||youtube.com/youtubei/v1/player/ad_break',
  '||www.youtube.com/get_midroll_',
  '||youtube.com/get_video_info?*=adunit&',
  '||youtube.com/get_video_info?*adunit',
  '||youtube.com/embed/*&origin=https%3A%2F%2Fwww.feltet.dk&widgetid=1$subdocument',
  '||youtube.com/embed/wqLWTeNBEEQ?',
  '||youtube.com/embed/-pGjd8-iyDQ',
  '||youtube.com/embed/46p5FwQdA64',
  '||youtube.com/embed/5tDSbsDqekU',
  '||youtube.com/embed/9olr5bechjI',
  '||youtube.com/embed/_6eiTXwuYoM',
  '||youtube.com/embed/CfBt63FbFNE',
  '||youtube.com/embed/dVD5yqGie9s',
  '||youtube.com/embed/GHomo-YgJNc',
  '||youtube.com/embed/h_PXz0vN5H4',
  '||youtube.com/embed/HF49uJ-e0zg',
  '||youtube.com/embed/Innx3oYcTWQ',
  '||youtube.com/embed/iNtajKR6ZCs',
  '||youtube.com/embed/iSsvK-L5CWI',
  '||youtube.com/embed/M63OoLc3WAI',
  '||youtube.com/embed/M6fO3qmXrhE',
  '||youtube.com/embed/MdidROnkjuo',
  '||youtube.com/embed/mILt9Fnh9bI',
  '||youtube.com/embed/Oknp4IAlagg',
  '||youtube.com/embed/qBR1xJA_nyY',
  '||youtube.com/embed/qZyibLqhGhs',
  '||youtube.com/embed/R5MZoHLaxCw',
  '||youtube.com/embed/r_MQnkukVrA',
  '||youtube.com/embed/SbtEQ5-Tzkc',
  '||youtube.com/embed/uETU52vKKOU',
  '||youtube.com/embed/VYuSDoPGeCk',
  '||youtube.com/embed/wr-wYUOdKi8',
  '||youtube.com/embed/zIQ6e--UWOw',
  '||youtube.com/embed/ZpENWJBmE10',
  '||youtube.com/embed/1ljpiLRAAho',
  '||youtube.com/embed/ixacW9YeJD0',
  '||youtube.com/embed/o19SibpQEcI',
  '||youtube.com/embed/Rr8SMpvYX2I?',
  '||youtube.com/embed/wuZ5Az_ANLU',
  '||googlesyndication.com^',
  '||googleads.g.doubleclick.net',
  '||doubleclick.com',
  '||google.com/pagead/',
  '||googlevideo.com/initplayback?source=youtube&*&c=TVHTML5&oad=$xmlhttprequest',
];


dynamicRules = makeDynamicRules(networkRulesFallback,domain)
//chrome.declarativeNetRequest.updateDynamicRules({addRules: dynamicRules,});


chrome.runtime.onInstalled.addListener(dynamicRules);
chrome.runtime.onStartup.addListener(dynamicRules);



// chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
//   if (message.action === "clickRefreshPage") {
//     // Inject code into the iframe
//     chrome.scripting.executeScript(
//       {
//         target: { tabId: sender.tab.id, allFrames: true },
//         func: () => {

//           let retries = 0;
//           const maxRetries = 20; // Retry for up to 5 seconds
//           var waitingForModalButton = setInterval(function () {
//             if (retries >= maxRetries) {
//               clearInterval(waitingForModalButton);
//               console.error("Button not found after maximum retries.");
//               return;
//             }
//             retries++;
//             const button = document.querySelector('button[jscontroller]');
//             if (button) {
//               clearInterval(waitingForModalButton);
//               const event = new PointerEvent('click', {
//                 bubbles: true,
//                 cancelable: true,
//                 composed: true,
//                 pointerType: 'mouse',
//               });
//               button.dispatchEvent(event);
//             }
//           }, 250);


//         },
//       },
//       () => {
//         sendResponse({ status: "success" });
//       }
//     );
//     return true;
//   }
// });

//let sessionMap = {};

// chrome.storage.session.get("sessionMap", (data) => {
//   sessionMap = data.sessionMap || {};
// });

// chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
//   if (tab.url && (tab.url.startsWith('chrome://') || tab.url.startsWith('edge://') || tab.url.startsWith('about:'))) {
//     return;
//   }

//   if (changeInfo.title && tab.url) {
//     try {
//       let previousMap = sessionMap[tabId] || '';
//       if (tab.url !== previousMap) {

//         sessionMap[tabId] = tab.url;
//         chrome.storage.session.set({ sessionMap });
//       }
//     } catch (error) {
//       console.error('Error processing tab URL:', error);
//     }
//   }
// });


chrome.runtime.onInstalled.addListener(onins);
chrome.commands.onCommand.addListener(kbshortcut);
chrome.storage.onChanged.addListener(handleStorageChanges);
chrome.runtime.onStartup.addListener(() => {
  setupAlarm();
  updateYouTubeBlockingScript();
  //createContextMenu();
  //updateRules();

});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name == 'getSwitches') {
    setSwitches();
  }
});

chrome.runtime.onMessage.addListener((request, sender) => {
  if (request.muteTab) {
    chrome.tabs.update(sender.tab.id, { muted: true });
  }
  else if (request.Unmute) {
    chrome.tabs.update(sender.tab.id, { muted: false });
  }
  else if (request.what == "insertCSS") {
    const tabId = sender?.tab?.id ?? false;
    const frameId = sender?.frameId ?? false;
    if (tabId === false || frameId === false) { return; }
    chrome.scripting.insertCSS({
      css: request.css,
      origin: 'USER',
      target: { tabId, frameIds: [frameId] },
    }).catch(reason => {
      console.log(reason);
    });
    return false;
  } 
  return true;
});

setSwitches();
setupAlarm();
//check_opt_eli();
updateYouTubeBlockingScript();
//createContextMenu();
//updateRules();
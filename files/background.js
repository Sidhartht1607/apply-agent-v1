// background.js — opens the sidebar when the extension icon is clicked
chrome.action.onClicked.addListener(tab => {
  chrome.sidePanel.open({ tabId: tab.id });
});

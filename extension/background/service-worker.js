/* Phantaslate background service worker.
 *
 * Clicking the toolbar icon opens the in-page panel (draggable, stays open
 * until closed). On pages where content scripts are not allowed — chrome://,
 * the Chrome Web Store, the PDF viewer, other extensions' pages — there is no
 * page to inject into, so we fall back to a standalone window that behaves the
 * same way: movable, and open until dismissed. */

"use strict";

const RESTRICTED = /^(chrome|edge|about|devtools|chrome-extension|view-source):|^https:\/\/chromewebstore\.google\.com|^https:\/\/chrome\.google\.com\/webstore/i;

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === "install") {
    chrome.storage.local.set({ source: "auto", target: "en" });
  }
});


chrome.runtime.onInstalled.addListener(async () => {
  const existing = await chrome.storage.local.get("installToken");
  if (!existing.installToken) {
    await chrome.storage.local.set({ installToken: crypto.randomUUID() });
  }
});


chrome.action.onClicked.addListener(async (tab) => {
  if (!tab || !tab.id || (tab.url && RESTRICTED.test(tab.url))) {
    return openStandaloneWindow();
  }

  try {
    await chrome.tabs.sendMessage(tab.id, { type: "phantaslate:toggle" });
  } catch {
    // Content script not present (page loaded before install, or injection
    // blocked). Try injecting once, then retry.
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["content/content.js"]
      });
      await chrome.tabs.sendMessage(tab.id, { type: "phantaslate:toggle" });
    } catch {
      openStandaloneWindow();
    }
  }
});

async function openStandaloneWindow() {
  // Reuse an existing standalone window if one is already open.
  const url = chrome.runtime.getURL("popup/popup.html");
  const existing = await chrome.windows.getAll({ populate: true });
  for (const win of existing) {
    if (win.type === "popup" && win.tabs && win.tabs.some((t) => t.url === url)) {
      return chrome.windows.update(win.id, { focused: true });
    }
  }
  chrome.windows.create({
    url,
    type: "popup",
    width: 392,
    height: 600
  });
}

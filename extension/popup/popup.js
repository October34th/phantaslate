/* Phantaslate popup — Stage 3.
 * Sends text to the relay and renders the translation. Nothing is stored except
 * your language choices and the relay URL (both local, via chrome.storage). */

"use strict";

// 9 languages, CJKV-first. "auto" is source-only.
const LANGUAGES = [
  { code: "auto",    name: "Auto-detect", sourceOnly: true },
  { code: "en",      name: "English" },
  { code: "zh-Hans", name: "Chinese (Simplified)" },
  { code: "zh-Hant", name: "Chinese (Traditional)" },
  { code: "ja",      name: "Japanese" },
  { code: "ko",      name: "Korean" },
  { code: "vi",      name: "Vietnamese" },
  { code: "es",      name: "Spanish" },
  { code: "fr",      name: "French" },
  { code: "de",      name: "German" }
];

const MAX_CHARS = 5000;
const DEFAULT_RELAY = "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 30000;
const DEFAULTS = {
  source: "auto",          // every session starts at Auto-detect …
  target: "en",            // … translating into English
  relayUrl: DEFAULT_RELAY,
  clearOnClose: true,
  rememberLangs: false     // languages reset on open unless opted in
};

const el = {
  source:     document.getElementById("sourceLang"),
  target:     document.getElementById("targetLang"),
  swap:       document.getElementById("swap"),
  input:      document.getElementById("input"),
  charCount:  document.getElementById("charCount"),
  translate:  document.getElementById("translate"),
  output:     document.getElementById("output"),
  resultWrap: document.getElementById("resultWrap"),
  copy:       document.getElementById("copy"),
  statusText: document.getElementById("statusText"),
  statusDot:  document.querySelector(".status__dot"),
  detected:   document.getElementById("detectedLang"),
  statusModel: document.getElementById("statusModel"),
  clear:       document.getElementById("clear"),
  clearOnClose: document.getElementById("clearOnClose"),
  rememberLangs: document.getElementById("rememberLangs"),
  mismatch:      document.getElementById("mismatch"),
  mismatchText:  document.getElementById("mismatchText"),
  mismatchUndo:  document.getElementById("mismatchUndo"),
  mismatchClose: document.getElementById("mismatchClose"),
  settings:       document.getElementById("settings"),
  settingsToggle: document.getElementById("settingsToggle"),
  relayUrl:       document.getElementById("relayUrl"),
  testRelay:      document.getElementById("testRelay")
};

let inFlight = null;   // AbortController for the active request
let sourceBeforeSwitch = null;   // for undoing an automatic language switch

/* ---------- Language dropdowns ---------- */
function populateSelect(select, includeAuto) {
  select.innerHTML = "";
  for (const lang of LANGUAGES) {
    if (lang.sourceOnly && !includeAuto) continue;
    const opt = document.createElement("option");
    opt.value = lang.code;
    opt.textContent = lang.name;
    select.appendChild(opt);
  }
}

/* ---------- Preferences ---------- */
function loadPrefs() {
  return new Promise((resolve) => {
    try {
      const keys = ["source", "target", "relayUrl", "clearOnClose", "rememberLangs"];
      chrome.storage.local.get(keys, (saved) => {
        el.relayUrl.value = saved.relayUrl || DEFAULTS.relayUrl;
        el.clearOnClose.checked =
          saved.clearOnClose === undefined ? DEFAULTS.clearOnClose : !!saved.clearOnClose;
        el.rememberLangs.checked = !!saved.rememberLangs;

        // Languages reset to Auto-detect -> English each time the panel opens,
        // unless the user has asked for them to be remembered.
        if (el.rememberLangs.checked) {
          el.source.value = saved.source || DEFAULTS.source;
          el.target.value = saved.target || DEFAULTS.target;
        } else {
          el.source.value = DEFAULTS.source;
          el.target.value = DEFAULTS.target;
        }
        resolve();
      });
    } catch {
      el.source.value   = DEFAULTS.source;
      el.target.value   = DEFAULTS.target;
      el.relayUrl.value = DEFAULTS.relayUrl;
      resolve();
    }
  });
}
function savePrefs() {
  try {
    const remember = !!el.rememberLangs.checked;
    chrome.storage.local.set({
      relayUrl: normalizeUrl(el.relayUrl.value),
      clearOnClose: !!el.clearOnClose.checked,
      rememberLangs: remember
    });
    if (remember) {
      chrome.storage.local.set({ source: el.source.value, target: el.target.value });
    } else {
      // Nothing to remember means nothing kept.
      chrome.storage.local.remove(["source", "target"]);
    }
  } catch { /* storage unavailable — ignore */ }
}

function normalizeUrl(value) {
  const url = (value || "").trim().replace(/\/+$/, "");
  return url || DEFAULT_RELAY;
}

/* ---------- Input state ---------- */
function updateCharCount() {
  const n = el.input.value.length;
  el.charCount.textContent = n + " / " + MAX_CHARS;
  el.charCount.classList.toggle("is-max", n >= MAX_CHARS);
}
function refreshButton() {
  el.translate.disabled = inFlight !== null || el.input.value.trim().length === 0;
}

/* ---------- Swap ---------- */
function swapLanguages() {
  const s = el.source.value;
  const t = el.target.value;
  if (s !== "auto") el.target.value = s;
  el.source.value = t;
  savePrefs();
}

/* ---------- Status pill ---------- */
function setStatus(text, state) {
  el.statusText.textContent = text;
  el.statusDot.className = "status__dot status__dot--" + state; // idle | ok | busy | error
}

/* Model name is shown separately so it survives status changes. */
function setModel(name) {
  if (!el.statusModel) return;
  if (name) {
    el.statusModel.textContent = "· " + name;
    el.statusModel.title = name;
    el.statusModel.removeAttribute("hidden");
  } else {
    el.statusModel.textContent = "";
    el.statusModel.removeAttribute("title");
    el.statusModel.setAttribute("hidden", "");
  }
}

/* ---------- Detected language chip ---------- */
function showDetected(name) {
  if (!el.detected) return;
  if (name && el.source.value === "auto") {
    el.detected.textContent = " · " + name;
    el.detected.removeAttribute("hidden");
  } else {
    clearDetected();
  }
}
function clearDetected() {
  if (!el.detected) return;
  el.detected.textContent = "";
  el.detected.setAttribute("hidden", "");
}

/* ---------- Relay calls ---------- */
async function checkHealth() {
  const base = normalizeUrl(el.relayUrl.value);
  setStatus("Checking…", "busy");
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(function () { ctrl.abort(); }, 5000);
    const res = await fetch(base + "/health", { signal: ctrl.signal });
    clearTimeout(timer);
    if (!res.ok) throw new Error("bad status");
    const data = await res.json();
    setStatus("Ready", "ok");
    setModel(data.model || "");
    return true;
  } catch {
    setStatus("Offline", "error");
    setModel("");
    return false;
  }
}

async function callRelay(text, source, target, signal) {
  const base = normalizeUrl(el.relayUrl.value);
  const res = await fetch(base + "/translate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: text, source_lang: source, target_lang: target }),
    signal: signal
  });

  if (!res.ok) {
    let detail = "";
    try {
      const err = await res.json();
      detail = err.detail || "";
    } catch { /* non-JSON error body */ }
    throw new Error(detail || ("Relay returned " + res.status + "."));
  }
  return res.json(); // -> { translation: "..." }
}

/* ---------- Translate ---------- */
async function onTranslate() {
  const text = el.input.value.trim();
  if (!text || inFlight) return;

  if (el.source.value !== "auto" && el.source.value === el.target.value) {
    showError("Source and target languages are the same.");
    return;
  }

  inFlight = new AbortController();
  const ctrl = inFlight;
  const timer = setTimeout(function () { ctrl.abort(); }, REQUEST_TIMEOUT_MS);
  setBusy(true);

  try {
    const data = await callRelay(text, el.source.value, el.target.value, ctrl.signal);
    showResult((data && data.translation) || "");
    handleDetection(data);
    setStatus("Translated · nothing stored", "ok");
  } catch (err) {
    if (err.name === "AbortError") {
      showError("Request timed out. Is the relay still running?");
    } else if (err instanceof TypeError) {
      // fetch() network-level failure — relay not reachable at all
      showError("Could not reach the relay at " + normalizeUrl(el.relayUrl.value) + ". Is it running?");
    } else {
      showError(err.message);
    }
    setStatus("Error", "error");
  } finally {
    clearTimeout(timer);
    inFlight = null;
    setBusy(false);
  }
}

function setBusy(busy) {
  el.translate.textContent = busy ? "Translating…" : "Translate";
  el.translate.classList.toggle("is-busy", busy);
  if (busy) setStatus("Translating…", "busy");
  refreshButton();
}

/* ---------- Language detection & mismatch ----------
 * The relay reports the language the text is actually written in on every
 * request. When the user has named a source language and the text disagrees,
 * say so — and switch to the real one rather than translating on a wrong
 * assumption. */
function nameForCode(code) {
  const hit = LANGUAGES.find(function (l) { return l.code === code; });
  return hit ? hit.name : code;
}
function hasOption(select, code) {
  return Array.prototype.some.call(select.options, function (o) { return o.value === code; });
}

function handleDetection(data) {
  const detectedName = data && data.detected_lang;
  const detectedCode = data && data.detected_code;
  const mismatch = !!(data && data.source_mismatch);

  // Auto-detect mode: just report what was found.
  if (el.source.value === "auto") {
    showDetected(detectedName);
    hideMismatch();
    return;
  }

  clearDetected();
  if (!mismatch || !detectedName) {
    hideMismatch();
    return;
  }

  const statedName = nameForCode(el.source.value);

  if (detectedCode && detectedCode === el.target.value) {
    // Switching would make source and target identical — warn only.
    showMismatch("This looks like " + detectedName + ", which is already your target language.", false);
  } else if (detectedCode && hasOption(el.source, detectedCode)) {
    sourceBeforeSwitch = el.source.value;
    el.source.value = detectedCode;
    savePrefs();
    showMismatch("Looks like " + detectedName + ", not " + statedName +
                 ". Switched From to " + detectedName + ".", true);
  } else {
    // Recognised as something we can't select — inform without changing state.
    showMismatch("This looks like " + detectedName + ", not " + statedName + ".", false);
  }
}

function showMismatch(message, undoable) {
  el.mismatchText.textContent = message;
  if (undoable) el.mismatchUndo.removeAttribute("hidden");
  else el.mismatchUndo.setAttribute("hidden", "");
  el.mismatch.removeAttribute("hidden");
}

function hideMismatch() {
  el.mismatch.setAttribute("hidden", "");
  el.mismatchUndo.setAttribute("hidden", "");
  sourceBeforeSwitch = null;
}

function undoSwitch() {
  if (sourceBeforeSwitch) {
    el.source.value = sourceBeforeSwitch;
    savePrefs();
  }
  hideMismatch();
}

/* ---------- Output ---------- */
function showResult(translation) {
  el.resultWrap.classList.remove("is-empty");
  el.output.classList.remove("is-notice", "is-error");
  el.output.textContent = translation;
  el.copy.disabled = !translation;
}
function showError(msg) {
  el.resultWrap.classList.remove("is-empty");
  el.output.classList.remove("is-notice");
  el.output.classList.add("is-error");
  el.output.textContent = msg;
  el.copy.disabled = true;
}

/* ---------- Clear ---------- */
function clearAll() {
  el.input.value = "";
  el.output.textContent = "Your translation will appear here.";
  el.output.classList.remove("is-error");
  el.output.classList.add("is-notice");
  el.resultWrap.classList.add("is-empty");
  el.copy.disabled = true;
  clearDetected();
  hideMismatch();
  updateCharCount();
  refreshButton();
}

/* ---------- Copy ---------- */
async function onCopy() {
  if (el.copy.disabled) return;
  const text = el.output.textContent || "";
  if (!text) return;
  const ok = await copyText(text);
  flashCopy(ok ? "Copied" : "Press Ctrl+C");
  if (!ok) selectOutput();   // leave it selected so Ctrl+C works
}

/* Two strategies: the async Clipboard API, then a synchronous execCommand
 * fallback for contexts where the API is unavailable or blocked. */
async function copyText(text) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* blocked or unavailable — try the fallback */ }

  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "0";
    ta.style.left = "-9999px";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    ta.setSelectionRange(0, ta.value.length);
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

function flashCopy(label) {
  const prev = "Copy";
  el.copy.textContent = label;
  setTimeout(function () { el.copy.textContent = prev; }, 1400);
}

/* Select the translation so the user can copy manually if both paths fail. */
function selectOutput() {
  try {
    const range = document.createRange();
    range.selectNodeContents(el.output);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  } catch { /* ignore */ }
}

/* ---------- Settings ---------- */
function toggleSettings() {
  const willOpen = el.settings.hasAttribute("hidden");
  if (willOpen) el.settings.removeAttribute("hidden");
  else el.settings.setAttribute("hidden", "");
  el.settingsToggle.setAttribute("aria-expanded", String(willOpen));
}

/* ---------- Init ---------- */
async function init() {
  populateSelect(el.source, true);
  populateSelect(el.target, false);
  await loadPrefs();
  updateCharCount();
  refreshButton();

  el.input.addEventListener("input", function () { updateCharCount(); refreshButton(); clearDetected(); hideMismatch(); });
  el.input.addEventListener("keydown", function (e) {
    // Ctrl/Cmd + Enter translates
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") onTranslate();
  });
  el.translate.addEventListener("click", onTranslate);
  el.swap.addEventListener("click", swapLanguages);
  el.copy.addEventListener("click", onCopy);
  el.clear.addEventListener("click", function () { clearAll(); el.input.focus(); });
  el.clearOnClose.addEventListener("change", savePrefs);
  el.rememberLangs.addEventListener("change", savePrefs);
  el.mismatchUndo.addEventListener("click", undoSwitch);
  el.mismatchClose.addEventListener("click", hideMismatch);
  el.source.addEventListener("change", function () { savePrefs(); clearDetected(); hideMismatch(); });
  el.target.addEventListener("change", savePrefs);
  el.settingsToggle.addEventListener("click", toggleSettings);
  el.testRelay.addEventListener("click", checkHealth);
  el.relayUrl.addEventListener("change", function () { savePrefs(); checkHealth(); });

  el.input.focus();
  checkHealth();   // reflect relay status on open
}

/* ---------- Panel integration ----------
 * When running inside the in-page panel, popup.html is embedded in an iframe.
 * The panel controls its own size; this layout stretches to fill whatever
 * height it is given, so there is never dead space below the content. */
const inPanel = window.parent !== window;

if (inPanel) {
  window.addEventListener("message", function (event) {
    const d = event.data;
    if (!d || d.source !== "phantaslate") return;
    if (d.type === "focus" && el.input) el.input.focus();
    // Panel closed: wipe the text unless the user opted to keep it.
    if (d.type === "closed" && el.clearOnClose && el.clearOnClose.checked) clearAll();
  });
}

document.addEventListener("DOMContentLoaded", init);

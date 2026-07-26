/* Phantaslate content script — draggable, resizable, persistent in-page panel.
 *
 * Chrome's toolbar popup can't be moved and closes on focus loss, so the panel
 * lives in the page instead. The panel is a host element with a shadow root
 * (so page CSS can't touch it) containing a drag bar, a close button, a resize
 * grip, and an iframe of popup.html — the translation UI stays one codebase.
 *
 * Position and size are remembered. The panel stays open until closed. */

"use strict";

(function () {
  // Guard against double-injection on soft navigations.
  if (window.__phantaslateInjected) return;
  window.__phantaslateInjected = true;

  const HOST_ID = "phantaslate-panel-host";
  const BAR_H = 34;
  const DEFAULT_W = 360;
  const DEFAULT_H = 520;
  const MIN_W = 320, MAX_W = 720;
  const MIN_H = 260, MAX_H = 900;
  const MARGIN = 16;

  let host = null, shadow = null, panel = null, frame = null, grip = null;
  let dragging = false, dragDX = 0, dragDY = 0;
  let resizing = false, resStartX = 0, resStartY = 0, resStartW = 0, resStartH = 0;
  let manualSize = false;   // once the user resizes, stop auto-fitting height

  /* ---------- Persistence ---------- */
  function savePosition(x, y) {
    try { chrome.storage.local.set({ panelPos: { x, y } }); } catch { /* ignore */ }
  }
  function saveSize(w, h) {
    try { chrome.storage.local.set({ panelSize: { w, h, manual: true } }); } catch { /* ignore */ }
  }
  function loadState() {
    return new Promise((resolve) => {
      try {
        chrome.storage.local.get(["panelPos", "panelSize"], (r) => resolve(r || {}));
      } catch { resolve({}); }
    });
  }

  function clampPos(x, y, w, h) {
    const maxX = Math.max(MARGIN, window.innerWidth - w - MARGIN);
    const maxY = Math.max(MARGIN, window.innerHeight - h - MARGIN);
    return {
      x: Math.min(Math.max(MARGIN, x), maxX),
      y: Math.min(Math.max(MARGIN, y), maxY)
    };
  }
  const clampW = (w) => Math.min(Math.max(MIN_W, w), MAX_W);
  const clampH = (h) => Math.min(Math.max(MIN_H, h), MAX_H);

  /* ---------- Build ---------- */
  async function buildPanel() {
    const state = await loadState();
    const size = state.panelSize || {};
    manualSize = !!size.manual;
    const startW = clampW(size.w || DEFAULT_W);
    const startH = clampH(size.h || DEFAULT_H);

    host = document.createElement("div");
    host.id = HOST_ID;
    host.style.cssText = "all: initial; position: fixed; top: 0; left: 0; width: 0; height: 0; z-index: 2147483647;";
    shadow = host.attachShadow({ mode: "open" });

    const style = document.createElement("style");
    style.textContent = `
      :host { all: initial; }
      * { box-sizing: border-box; margin: 0; padding: 0; }

      .panel {
        position: fixed;
        width: ${startW}px;
        background: #ffffff;
        border: 1px solid #e2e7f0;
        border-radius: 14px;
        box-shadow: 0 12px 40px rgba(12, 28, 68, 0.28), 0 2px 8px rgba(12, 28, 68, 0.12);
        overflow: hidden;
        font-family: "Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif;
      }
      .panel.is-dragging, .panel.is-resizing { user-select: none; }
      .panel.is-dragging .frame,
      .panel.is-resizing .frame { pointer-events: none; }

      .bar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        height: ${BAR_H}px;
        padding: 0 8px 0 12px;
        background: #0D2045;
        cursor: grab;
      }
      .bar:active { cursor: grabbing; }
      .bar__title {
        display: flex; align-items: center; gap: 7px;
        font-size: 11px; font-weight: 600;
        letter-spacing: 0.08em; text-transform: uppercase;
        color: #ffffff; opacity: .92;
        pointer-events: none;
      }
      .bar__grip { display: block; width: 12px; height: 12px; opacity: .55; }
      .bar__close {
        display: grid; place-items: center;
        width: 22px; height: 22px;
        color: #ffffff; background: transparent;
        border: none; border-radius: 6px;
        cursor: pointer; opacity: .75;
        transition: background .15s, opacity .15s;
      }
      .bar__close:hover { background: rgba(255,255,255,.16); opacity: 1; }

      .frame {
        display: block;
        width: 100%;
        height: ${startH}px;
        border: 0;
        background: #ffffff;
      }

      .resize {
        position: absolute;
        right: 0; bottom: 0;
        width: 18px; height: 18px;
        cursor: nwse-resize;
        color: #6b7793;
        opacity: .6;
        background: transparent;
        border: none;
        padding: 0;
        display: grid;
        place-items: center;
      }
      .resize:hover { opacity: 1; color: #058F8D; }
    `;

    panel = document.createElement("div");
    panel.className = "panel";

    const bar = document.createElement("div");
    bar.className = "bar";
    bar.innerHTML = `
      <span class="bar__title">
        <svg class="bar__grip" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <circle cx="9" cy="6" r="1.6"/><circle cx="15" cy="6" r="1.6"/>
          <circle cx="9" cy="12" r="1.6"/><circle cx="15" cy="12" r="1.6"/>
          <circle cx="9" cy="18" r="1.6"/><circle cx="15" cy="18" r="1.6"/>
        </svg>
        Phantaslate
      </span>
      <button class="bar__close" type="button" aria-label="Close" title="Close">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"
             stroke-width="2.4" stroke-linecap="round" aria-hidden="true">
          <path d="M6 6l12 12M18 6L6 18"/>
        </svg>
      </button>
    `;

    frame = document.createElement("iframe");
    frame.className = "frame";
    frame.setAttribute("title", "Phantaslate");
    // Cross-origin iframes are denied the async Clipboard API unless the
    // embedder delegates it explicitly. Without this, Copy silently fails.
    frame.setAttribute("allow", "clipboard-write");
    frame.src = chrome.runtime.getURL("popup/popup.html");

    grip = document.createElement("button");
    grip.className = "resize";
    grip.type = "button";
    grip.setAttribute("aria-label", "Resize panel");
    grip.title = "Drag to resize · double-click to reset";
    grip.innerHTML = `
      <svg viewBox="0 0 12 12" width="11" height="11" fill="currentColor" aria-hidden="true">
        <circle cx="9.5" cy="2.5" r="1"/><circle cx="9.5" cy="6" r="1"/><circle cx="6" cy="9.5" r="1"/>
        <circle cx="9.5" cy="9.5" r="1"/><circle cx="2.5" cy="9.5" r="1"/><circle cx="6" cy="6" r="1"/>
      </svg>
    `;

    panel.appendChild(bar);
    panel.appendChild(frame);
    panel.appendChild(grip);
    shadow.appendChild(style);
    shadow.appendChild(panel);
    document.documentElement.appendChild(host);

    // Restore position, else park top-right.
    const saved = state.panelPos;
    const start = saved || { x: window.innerWidth - startW - 24, y: 24 };
    const pos = clampPos(start.x, start.y, startW, startH + BAR_H);
    panel.style.left = pos.x + "px";
    panel.style.top = pos.y + "px";

    bar.addEventListener("mousedown", onDragStart);
    bar.querySelector(".bar__close").addEventListener("click", (e) => {
      e.stopPropagation();
      closePanel();
    });
    grip.addEventListener("mousedown", onResizeStart);
    grip.addEventListener("dblclick", resetToAutoSize);
  }

  /* ---------- Dragging ---------- */
  function onDragStart(e) {
    if (e.button !== 0 || e.target.closest(".bar__close")) return;
    dragging = true;
    const rect = panel.getBoundingClientRect();
    dragDX = e.clientX - rect.left;
    dragDY = e.clientY - rect.top;
    panel.classList.add("is-dragging");
    window.addEventListener("mousemove", onDragMove, true);
    window.addEventListener("mouseup", onDragEnd, true);
    e.preventDefault();
  }
  function onDragMove(e) {
    if (!dragging) return;
    const rect = panel.getBoundingClientRect();
    const pos = clampPos(e.clientX - dragDX, e.clientY - dragDY, rect.width, rect.height);
    panel.style.left = pos.x + "px";
    panel.style.top = pos.y + "px";
  }
  function onDragEnd() {
    if (!dragging) return;
    dragging = false;
    panel.classList.remove("is-dragging");
    window.removeEventListener("mousemove", onDragMove, true);
    window.removeEventListener("mouseup", onDragEnd, true);
    const rect = panel.getBoundingClientRect();
    savePosition(rect.left, rect.top);
  }

  /* ---------- Resizing ---------- */
  function onResizeStart(e) {
    if (e.button !== 0) return;
    resizing = true;
    manualSize = true;                      // user takes control of the size
    const rect = panel.getBoundingClientRect();
    resStartX = e.clientX;
    resStartY = e.clientY;
    resStartW = rect.width;
    resStartH = frame.getBoundingClientRect().height;
    panel.classList.add("is-resizing");
    window.addEventListener("mousemove", onResizeMove, true);
    window.addEventListener("mouseup", onResizeEnd, true);
    e.preventDefault();
    e.stopPropagation();
  }
  function onResizeMove(e) {
    if (!resizing) return;
    const w = clampW(resStartW + (e.clientX - resStartX));
    const h = clampH(resStartH + (e.clientY - resStartY));
    panel.style.width = w + "px";
    frame.style.height = h + "px";
  }
  function onResizeEnd() {
    if (!resizing) return;
    resizing = false;
    panel.classList.remove("is-resizing");
    window.removeEventListener("mousemove", onResizeMove, true);
    window.removeEventListener("mouseup", onResizeEnd, true);
    const w = panel.getBoundingClientRect().width;
    const h = frame.getBoundingClientRect().height;
    saveSize(Math.round(w), Math.round(h));
  }

  /* Double-click the grip: restore the default size. */
  function resetToAutoSize() {
    manualSize = false;
    panel.style.width = DEFAULT_W + "px";
    frame.style.height = DEFAULT_H + "px";
    try { chrome.storage.local.set({ panelSize: { w: DEFAULT_W, h: DEFAULT_H, manual: false } }); } catch { /* ignore */ }
  }

  /* ---------- Open / close ---------- */
  function post(type) {
    try { frame.contentWindow.postMessage({ source: "phantaslate", type }, "*"); } catch { /* ignore */ }
  }

  async function openPanel() {
    if (!host) await buildPanel();
    host.style.display = "";
    post("focus");
  }

  function closePanel() {
    if (!host) return;
    // Tell the UI it was closed so it can wipe the text (privacy default).
    post("closed");
    host.style.display = "none";
  }

  function isOpen() { return !!host && host.style.display !== "none"; }

  async function togglePanel() {
    if (isOpen()) closePanel();
    else await openPanel();
  }

  /* ---------- Messages ---------- */
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg && msg.type === "phantaslate:toggle") {
      togglePanel();
      sendResponse({ ok: true });
    }
    return false;
  });

  window.addEventListener("message", (event) => {
    const d = event.data;
    if (!d || d.source !== "phantaslate") return;
    if (d.type === "close") closePanel();
  });

  window.addEventListener("resize", () => {
    if (!isOpen()) return;
    const rect = panel.getBoundingClientRect();
    const pos = clampPos(rect.left, rect.top, rect.width, rect.height);
    panel.style.left = pos.x + "px";
    panel.style.top = pos.y + "px";
  });
})();

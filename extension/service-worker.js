// chrome-bridge service worker
// Polls localhost relay for jobs, dispatches to chrome.* APIs, returns results.
// MV3 service worker keepalive: chrome.alarms re-wakes every 25s.

const RELAY = "http://127.0.0.1:9224";
const STEALTH_DOMAINS = new Set([
  "linkedin.com",       // Tier-A: clipboard-handoff only, never touched here
  "www.linkedin.com",
  "bank",               // pseudo-token; real list in storage
]);

// Defense-in-depth: refuse jobs that target stealth domains even if relay sent them.
function isStealthBlocked(url) {
  try {
    const u = new URL(url);
    return [...STEALTH_DOMAINS].some(d => u.hostname === d || u.hostname.endsWith("." + d));
  } catch { return false; }
}

// === Job dispatch ============================================================

async function handleJob(job) {
  const { kind, args = {} } = job;
  switch (kind) {
    case "ping":
      return { ok: true, ua: navigator.userAgent, ts: Date.now() };

    case "cookies": {
      const { url, name } = args;
      if (isStealthBlocked(url)) return { ok: false, error: "stealth-blocked", url };
      const cookies = name
        ? [await chrome.cookies.get({ url, name })]
        : await chrome.cookies.getAll({ url });
      return { ok: true, cookies };
    }

    case "gql": {
      const { url, query, variables, bearer, alias } = args;
      if (isStealthBlocked(url)) return { ok: false, error: "stealth-blocked", url };
      const u = alias ? `${url}?alias=${encodeURIComponent(alias)}` : url;
      const headers = { "Content-Type": "application/json" };
      if (bearer) headers["Authorization"] = `Bearer ${bearer}`;
      const r = await fetch(u, {
        method: "POST",
        credentials: "include",
        headers,
        body: JSON.stringify({ query, variables }),
      });
      const text = await r.text();
      let json = null;
      try { json = JSON.parse(text); } catch {}
      return { ok: true, status: r.status, json, text: json ? null : text };
    }

    case "tabs.query": {
      const tabs = await chrome.tabs.query(args.query || {});
      return { ok: true, tabs: tabs.map(t => ({ id: t.id, url: t.url, title: t.title, active: t.active })) };
    }

    case "tabs.create": {
      const { url, active = false } = args;
      if (url && isStealthBlocked(url)) return { ok: false, error: "stealth-blocked", url };
      const t = await chrome.tabs.create({ url, active });
      return { ok: true, tab: { id: t.id, url: t.url } };
    }

    case "tabs.update": {
      const { tabId, url, active } = args;
      if (url && isStealthBlocked(url)) return { ok: false, error: "stealth-blocked", url };
      const t = await chrome.tabs.update(tabId, { url, active });
      return { ok: true, tab: { id: t.id, url: t.url } };
    }

    case "scripting.eval": {
      const { tabId, code, world = "MAIN" } = args;
      const tab = await chrome.tabs.get(tabId);
      if (isStealthBlocked(tab.url)) return { ok: false, error: "stealth-blocked", url: tab.url };
      const [{ result } = {}] = await chrome.scripting.executeScript({
        target: { tabId },
        world,
        func: (src) => {
          // eslint-disable-next-line no-new-func
          return Promise.resolve((async () => (0, eval)(src))()).then(v => v);
        },
        args: [code],
      });
      return { ok: true, result };
    }

    case "capture.install": {
      // Inject MAIN-world fetch interceptor. Records outgoing fetches matching `pattern`.
      const { tabId, pattern } = args;
      const tab = await chrome.tabs.get(tabId);
      if (isStealthBlocked(tab.url)) return { ok: false, error: "stealth-blocked", url: tab.url };
      await chrome.scripting.executeScript({
        target: { tabId },
        world: "MAIN",
        files: ["main-world-capture.js"],
      });
      // Tell the page-script which pattern to record.
      await chrome.scripting.executeScript({
        target: { tabId },
        world: "MAIN",
        func: (p) => { window.__cbCapturePattern = p; window.__cbCapturedRequests = []; },
        args: [pattern || ""],
      });
      return { ok: true };
    }

    case "capture.drain": {
      const { tabId } = args;
      const [{ result } = {}] = await chrome.scripting.executeScript({
        target: { tabId },
        world: "MAIN",
        func: () => {
          const out = window.__cbCapturedRequests || [];
          window.__cbCapturedRequests = [];
          return out;
        },
      });
      return { ok: true, captured: result || [] };
    }

    case "network.start": {
      // chrome.webRequest catches every request the renderer makes — survives
      // page reloads + races; doesn't depend on in-page JS install order.
      const { urlPatterns = ["<all_urls>"] } = args;
      if (!self.__cbNet) self.__cbNet = { listeners: [], records: [] };
      const onBefore = (details) => {
        if (details.method !== "POST" && details.method !== "GET") return;
        const rec = {
          ts: Date.now(),
          method: details.method,
          url: details.url,
          type: details.type,
          tabId: details.tabId,
        };
        if (details.requestBody) {
          if (details.requestBody.raw) {
            try {
              rec.body = details.requestBody.raw
                .map(r => new TextDecoder().decode(r.bytes))
                .join("");
            } catch {}
          } else if (details.requestBody.formData) {
            rec.body = JSON.stringify(details.requestBody.formData);
          }
        }
        self.__cbNet.records.push(rec);
        if (self.__cbNet.records.length > 5000) self.__cbNet.records.shift();
      };
      chrome.webRequest.onBeforeRequest.addListener(
        onBefore,
        { urls: urlPatterns },
        ["requestBody"]
      );
      self.__cbNet.listeners.push(onBefore);
      return { ok: true, listeners: self.__cbNet.listeners.length };
    }

    case "network.drain": {
      if (!self.__cbNet) return { ok: true, records: [] };
      const recs = self.__cbNet.records;
      self.__cbNet.records = [];
      return { ok: true, records: recs };
    }

    case "network.stop": {
      if (!self.__cbNet) return { ok: true };
      for (const fn of self.__cbNet.listeners) {
        try { chrome.webRequest.onBeforeRequest.removeListener(fn); } catch {}
      }
      self.__cbNet = { listeners: [], records: [] };
      return { ok: true };
    }

    case "debugger.click": {
      // Tier-B only: chrome.debugger Input.dispatchMouseEvent at coords.
      const { tabId, x, y } = args;
      const tab = await chrome.tabs.get(tabId);
      if (isStealthBlocked(tab.url)) return { ok: false, error: "stealth-blocked", url: tab.url };
      await chrome.debugger.attach({ tabId }, "1.3");
      try {
        await chrome.debugger.sendCommand({ tabId }, "Input.dispatchMouseEvent",
          { type: "mousePressed", x, y, button: "left", clickCount: 1, buttons: 1 });
        await chrome.debugger.sendCommand({ tabId }, "Input.dispatchMouseEvent",
          { type: "mouseReleased", x, y, button: "left", clickCount: 1, buttons: 0 });
      } finally {
        await chrome.debugger.detach({ tabId });
      }
      return { ok: true };
    }

    case "debugger.type": {
      const { tabId, text, mode = "keyEvent" } = args;
      const tab = await chrome.tabs.get(tabId);
      if (isStealthBlocked(tab.url)) return { ok: false, error: "stealth-blocked", url: tab.url };
      await chrome.debugger.attach({ tabId }, "1.3");
      try {
        if (mode === "insertText") {
          // Fast path — fires `input` event but no `keydown`. Some inputs OK with this.
          for (const ch of text) {
            await chrome.debugger.sendCommand({ tabId }, "Input.insertText", { text: ch });
            await new Promise(r => setTimeout(r, 30 + Math.random() * 80));
          }
        } else {
          // Default — full keydown/char/keyup chain. Vue/React typeaheads (Algolia,
          // air3-typeahead-input) listen on keydown + input; insertText alone is dropped.
          for (const ch of text) {
            const code = keyCodeFor(ch);
            // keyDown WITHOUT text — fires keydown only, no input
            await chrome.debugger.sendCommand({ tabId }, "Input.dispatchKeyEvent", {
              type: "keyDown",
              key: ch, code, windowsVirtualKeyCode: code.length === 1 ? ch.charCodeAt(0) : 0,
            });
            // char with text — fires keypress + input event with the char
            await chrome.debugger.sendCommand({ tabId }, "Input.dispatchKeyEvent", {
              type: "char", text: ch, unmodifiedText: ch, key: ch, code,
            });
            // keyUp
            await chrome.debugger.sendCommand({ tabId }, "Input.dispatchKeyEvent", {
              type: "keyUp", key: ch, code,
            });
            // Default jitter is short — typeaheads don't care for textareas, and
            // overall throughput matters when descriptions are 500+ chars.
            await new Promise(r => setTimeout(r, 5 + Math.random() * 15));
          }
        }
      } finally {
        await chrome.debugger.detach({ tabId });
      }
      return { ok: true };
    }

    default:
      return { ok: false, error: "unknown-kind", kind };
  }
}

// === Polling loop ============================================================

let pollInflight = false;

async function pollOnce() {
  if (pollInflight) return;
  pollInflight = true;
  try {
    const r = await fetch(`${RELAY}/poll?wait=20`, { method: "GET" });
    if (r.status === 204) return;            // no job
    if (!r.ok) { await sleep(2000); return; } // relay down, back off
    const job = await r.json();
    let result;
    try {
      result = await handleJob(job);
    } catch (e) {
      result = { ok: false, error: String(e), stack: e?.stack };
    }
    await fetch(`${RELAY}/result/${job.id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(result),
    });
  } catch (e) {
    // relay unreachable; service worker will retry on next alarm
    console.warn("[cb] poll error", e);
  } finally {
    pollInflight = false;
  }
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// Map a character to a CDP `code` value (US keyboard layout for ASCII).
function keyCodeFor(ch) {
  if (/[a-z]/.test(ch)) return "Key" + ch.toUpperCase();
  if (/[A-Z]/.test(ch)) return "Key" + ch;
  if (/[0-9]/.test(ch)) return "Digit" + ch;
  const map = {
    " ": "Space", ".": "Period", ",": "Comma", "-": "Minus", "_": "Minus",
    "/": "Slash", "\\": "Backslash", ";": "Semicolon", "'": "Quote",
    "[": "BracketLeft", "]": "BracketRight", "`": "Backquote",
    "=": "Equal", "+": "Equal",
    "\n": "Enter", "\t": "Tab",
  };
  return map[ch] || ch;
}

chrome.alarms.create("cb-poll", { periodInMinutes: 0.4 });
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === "cb-poll") pollOnce();
});

chrome.runtime.onInstalled.addListener(() => pollOnce());
chrome.runtime.onStartup.addListener(() => pollOnce());

// Also poll continuously in tight loop while SW is alive.
(async function tight() {
  while (true) {
    await pollOnce();
    await sleep(500);
  }
})();

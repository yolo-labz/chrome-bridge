// main-world-capture.js
// Runs in the page's own JS context (world: "MAIN").
// Wraps window.fetch and XHR.send to record outgoing requests matching window.__cbCapturePattern.
// Activated by service-worker via chrome.scripting.executeScript({world:"MAIN", files:[...]}).

(function () {
  if (window.__cbCaptureInstalled) return;
  window.__cbCaptureInstalled = true;
  window.__cbCapturedRequests = window.__cbCapturedRequests || [];

  function matches(url) {
    const p = window.__cbCapturePattern || "";
    if (!p) return true;
    try {
      if (p.startsWith("re:")) return new RegExp(p.slice(3)).test(url);
      return url.includes(p);
    } catch { return false; }
  }

  const origFetch = window.fetch.bind(window);
  window.fetch = async function (resource, init) {
    const url = typeof resource === "string" ? resource : resource.url;
    let bodyText = null;
    if (init && init.body) {
      try { bodyText = typeof init.body === "string" ? init.body : new TextDecoder().decode(await new Response(init.body).arrayBuffer()); } catch {}
    } else if (resource instanceof Request && resource.bodyUsed === false) {
      try { bodyText = await resource.clone().text(); } catch {}
    }
    if (matches(url)) {
      window.__cbCapturedRequests.push({
        ts: Date.now(),
        kind: "fetch",
        url,
        method: (init && init.method) || (resource instanceof Request ? resource.method : "GET"),
        headers: headersToObject((init && init.headers) || (resource instanceof Request ? resource.headers : {})),
        body: bodyText,
      });
    }
    return origFetch(resource, init);
  };

  function headersToObject(h) {
    if (!h) return {};
    if (h instanceof Headers) {
      const o = {}; for (const [k, v] of h.entries()) o[k] = v; return o;
    }
    if (Array.isArray(h)) return Object.fromEntries(h);
    return { ...h };
  }

  const origXHRSend = XMLHttpRequest.prototype.send;
  const origXHROpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__cbMethod = method;
    this.__cbURL = url;
    return origXHROpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function (body) {
    if (this.__cbURL && matches(this.__cbURL)) {
      let bodyText = null;
      try { bodyText = typeof body === "string" ? body : (body ? "[binary]" : null); } catch {}
      window.__cbCapturedRequests.push({
        ts: Date.now(),
        kind: "xhr",
        url: this.__cbURL,
        method: this.__cbMethod || "GET",
        body: bodyText,
      });
    }
    return origXHRSend.apply(this, arguments);
  };

  console.log("[cb] capture installed; pattern=", window.__cbCapturePattern || "(any)");
})();

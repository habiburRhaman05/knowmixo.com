/*!
 * Knowmivo embed widget. Public domain usage.
 *
 * Usage:
 *   <script src="https://knowmivo.com/embed.js"
 *           data-bot-id="pub_abc123"
 *           data-api="https://knowmivo.com" async></script>
 *
 * What this does:
 *  - Finds its own <script> tag, reads data-* attributes.
 *  - Injects a floating launcher button (bottom-right by default).
 *  - On click, injects a sandboxed <iframe> pointed at /widget/<publicId>.
 *  - Listens for postMessage from the iframe (kmv:ready, kmv:size, kmv:close).
 *
 * Deliberately no owner credentials, no window.knowmivo config besides public
 * ids, and no third-party dependencies. The iframe itself talks to our
 * backend; this script's sole job is lifecycle + postMessage + styling.
 */
(function () {
  "use strict";
  if (window.__knowmivoEmbedded) return;
  window.__knowmivoEmbedded = true;

  var currentScript =
    document.currentScript ||
    (function () {
      var scripts = document.getElementsByTagName("script");
      for (var i = scripts.length - 1; i >= 0; i--) {
        var src = scripts[i].src || "";
        if (/embed\.js(\?|$)/.test(src)) return scripts[i];
      }
      return null;
    })();
  if (!currentScript) return;

  var publicId = currentScript.getAttribute("data-bot-id") || "";
  var apiBase =
    currentScript.getAttribute("data-api") ||
    (function () {
      try {
        var u = new URL(currentScript.src);
        return u.origin;
      } catch (_) {
        return "";
      }
    })();
  var position = (currentScript.getAttribute("data-position") || "bottom-right").toLowerCase();
  if (!publicId || !apiBase) {
    if (window.console && console.warn) {
      console.warn("[knowmivo] embed.js is missing data-bot-id or data-api");
    }
    return;
  }

  var widgetOrigin = apiBase.replace(/\/$/, "");
  var iframeUrl = widgetOrigin + "/widget/" + encodeURIComponent(publicId);

  // --- Styles ------------------------------------------------------------
  var styleId = "kmv-embed-styles";
  if (!document.getElementById(styleId)) {
    var style = document.createElement("style");
    style.id = styleId;
    style.textContent = [
      ".kmv-launcher{position:fixed;" +
        (position === "bottom-left" ? "left:16px;" : "right:16px;") +
        "bottom:16px;z-index:2147483646;width:56px;height:56px;border-radius:999px;" +
        "border:none;background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;" +
        "box-shadow:0 10px 24px -8px rgba(79,70,229,.6);cursor:pointer;display:flex;" +
        "align-items:center;justify-content:center;transition:transform .15s ease;}",
      ".kmv-launcher:hover{transform:scale(1.04);}",
      ".kmv-launcher:focus-visible{outline:3px solid rgba(79,70,229,.45);outline-offset:2px;}",
      ".kmv-launcher svg{width:24px;height:24px;}",
      ".kmv-frame{position:fixed;" +
        (position === "bottom-left" ? "left:16px;" : "right:16px;") +
        "bottom:88px;z-index:2147483647;width:min(400px,calc(100vw - 24px));" +
        "height:min(640px,calc(100vh - 120px));border:none;border-radius:16px;" +
        "box-shadow:0 24px 48px -12px rgba(16,24,40,.25);background:transparent;" +
        "opacity:0;transform:translateY(8px);pointer-events:none;" +
        "transition:opacity .15s ease,transform .15s ease;}",
      ".kmv-frame.kmv-open{opacity:1;transform:translateY(0);pointer-events:auto;}",
      "@media (max-width:480px){.kmv-frame{width:calc(100vw - 16px);height:calc(100vh - 96px);bottom:80px;" +
        (position === "bottom-left" ? "left:8px;" : "right:8px;") + "}}",
      "@media (prefers-reduced-motion:reduce){.kmv-launcher,.kmv-frame{transition:none;}}",
    ].join("\n");
    document.head.appendChild(style);
  }

  // --- Launcher button ---------------------------------------------------
  var launcher = document.createElement("button");
  launcher.type = "button";
  launcher.className = "kmv-launcher";
  launcher.setAttribute("aria-label", "Open chat");
  launcher.setAttribute("aria-haspopup", "dialog");
  launcher.setAttribute("aria-expanded", "false");
  launcher.innerHTML =
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
    '<path d="M4 6a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3v7a3 3 0 0 1-3 3H10l-5 4v-4H7a3 3 0 0 1-3-3V6Z" fill="currentColor" opacity=".25"/>' +
    '<path d="M8 10h8M8 13h5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' +
    "</svg>";
  document.body.appendChild(launcher);

  // --- Iframe (lazy) -----------------------------------------------------
  var iframe = null;
  var opened = false;

  function createIframe() {
    if (iframe) return iframe;
    iframe = document.createElement("iframe");
    iframe.className = "kmv-frame";
    iframe.src = iframeUrl;
    iframe.title = "Knowmivo chat";
    // No allow-same-origin: the widget talks to its own backend, not the
    // host's. Scripts and forms are needed; popups aren't.
    iframe.setAttribute("sandbox", "allow-scripts allow-forms");
    iframe.setAttribute(
      "allow",
      "clipboard-write; encrypted-media"
    );
    document.body.appendChild(iframe);
    return iframe;
  }

  function open() {
    if (opened) return;
    var frame = createIframe();
    requestAnimationFrame(function () {
      frame.classList.add("kmv-open");
    });
    opened = true;
    launcher.setAttribute("aria-expanded", "true");
    launcher.setAttribute("aria-label", "Close chat");
    try {
      frame.contentWindow && frame.contentWindow.postMessage({ type: "kmv:open" }, widgetOrigin);
    } catch (_) {}
  }

  function close() {
    if (!opened || !iframe) return;
    iframe.classList.remove("kmv-open");
    opened = false;
    launcher.setAttribute("aria-expanded", "false");
    launcher.setAttribute("aria-label", "Open chat");
    try {
      iframe.contentWindow && iframe.contentWindow.postMessage({ type: "kmv:close" }, widgetOrigin);
    } catch (_) {}
  }

  launcher.addEventListener("click", function () {
    opened ? close() : open();
  });

  // --- postMessage -------------------------------------------------------
  window.addEventListener("message", function (event) {
    if (event.origin !== widgetOrigin) return;
    var data = event.data || {};
    if (data.type === "kmv:ready") {
      // Iframe is live. Nothing to do yet.
    } else if (data.type === "kmv:close") {
      close();
    }
  });

  // --- Public API --------------------------------------------------------
  window.Knowmivo = {
    open: open,
    close: close,
    toggle: function () {
      opened ? close() : open();
    },
    version: "1",
  };
})();

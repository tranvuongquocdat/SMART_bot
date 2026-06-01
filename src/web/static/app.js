// HTMX bootstrap + small UI helpers.
// Tailwind/HTMX/Alpine are loaded via CDN in base.html.
(function () {
  function setHeader(e) {
    const meta = document.querySelector('meta[name=csrf-token]');
    if (meta) e.detail.headers["X-CSRF-Token"] = meta.content;
  }
  document.addEventListener("DOMContentLoaded", function () {
    if (window.htmx) {
      htmx.on("htmx:configRequest", setHeader);
    }
  });
})();

(function () {
  var meta = document.querySelector('meta[name="csrf-token"]');
  if (!meta || !meta.content) return;
  var token = meta.content;

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": token
      },
      credentials: "same-origin",
      body: JSON.stringify(body || {})
    });
  }

  post("/api/analytics/page", {
    path: window.location.pathname + window.location.search,
    referrer: document.referrer || ""
  });

  window.setInterval(function () {
    if (document.visibilityState === "hidden") return;
    post("/api/analytics/heartbeat", {
      path: window.location.pathname + window.location.search
    });
  }, 30000);
})();

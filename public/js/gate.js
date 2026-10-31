(function () {
  var gate = document.getElementById("gate");
  var button = document.getElementById("gate-enable");
  var status = document.getElementById("gate-status");
  var token = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  var busy = false;

  function setState(name, message, isError) {
    gate.dataset.state = name;
    status.textContent = message || "";
    status.classList.toggle("is-error", !!isError);
  }

  function report(outcome) {
    if (!token) return;
    fetch("/api/access/outcome", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
      credentials: "same-origin",
      body: JSON.stringify({ status: outcome })
    }).catch(function () {});
  }

  function classifyDenial(done) {
    if (!navigator.permissions || !navigator.permissions.query) {
      done("denied");
      return;
    }
    navigator.permissions.query({ name: "geolocation" }).then(function (result) {
      done(result.state === "prompt" ? "dismissed" : "denied");
    }).catch(function () { done("denied"); });
  }

  function requestLocation() {
    if (busy) return;
    if (!window.isSecureContext) {
      setState("BROWSER_UNSUPPORTED", "Browser location only works on a secure https connection, or on localhost. Open this site with https.", true);
      button.disabled = true;
      return;
    }
    if (!navigator.geolocation) {
      setState("BROWSER_UNSUPPORTED", "This browser cannot share location, so this portfolio cannot be opened here. Try a current version of Chrome, Edge, or Safari.", true);
      report("unsupported");
      button.disabled = true;
      return;
    }
    busy = true;
    button.disabled = true;
    setState("REQUESTING_LOCATION", "Waiting for the browser’s own location prompt…");
    navigator.geolocation.getCurrentPosition(function (position) {
      setState("RECORDING_VISITOR", "Saving this one-time location…");
      var coords = position.coords || {};
      fetch("/api/access/location", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
        credentials: "same-origin",
        body: JSON.stringify({
          latitude: coords.latitude,
          longitude: coords.longitude,
          accuracy: coords.accuracy,
          timestamp: position.timestamp,
          timezone: (Intl.DateTimeFormat().resolvedOptions() || {}).timeZone || "",
          language: navigator.language || "",
          screen: screen.width + "x" + screen.height,
          viewport: window.innerWidth + "x" + window.innerHeight
        })
      }).then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, data: data };
        });
      }).then(function (result) {
        if (!result.ok || !result.data.unlocked) {
          throw new Error((result.data && result.data.error) || "server");
        }
        setState("ACCESS_GRANTED", "Opening the portfolio…");
        gate.classList.add("is-unlocking");
        window.location.reload();
      }).catch(function (error) {
        busy = false;
        button.disabled = false;
        setState("SERVER_ERROR", error.message && error.message !== "server" ? error.message : "The server could not save the location check. Nothing was unlocked. Try again in a moment.", true);
      });
    }, function (error) {
      busy = false;
      button.disabled = false;
      if (error && error.code === 1) {
        classifyDenial(function (kind) {
          if (kind === "dismissed") {
            setState("PERMISSION_DENIED", "The location prompt was dismissed. Permission is required to view this portfolio. You can try again when you are ready.", true);
            report("dismissed");
          } else {
            setState("PERMISSION_DENIED", "Location permission is blocked for this site, so the portfolio stays closed. Allow location for this site in the browser settings, then retry.", true);
            report("denied");
          }
        });
        return;
      }
      if (error && error.code === 3) {
        setState("LOCATION_TIMEOUT", "The location request timed out. Try again when the signal is clearer.", true);
        report("timeout");
        return;
      }
      setState("LOCATION_UNAVAILABLE", "The browser could not determine a location. Check that location services are on, then retry.", true);
      report("unavailable");
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
  }

  button.addEventListener("click", requestLocation);

  if (document.body.dataset.rateLimited === "1") {
    setState("SERVER_ERROR", "Too many attempts from this network. Wait a little while, then reload this page.", true);
    button.disabled = true;
    return;
  }

  setState("INITIALIZING", "");
  if (!window.isSecureContext) {
    setState("BROWSER_UNSUPPORTED", "Browser location only works on a secure https connection, or on localhost. Open this site with https.", true);
    button.disabled = true;
    return;
  }
  if (!navigator.geolocation) {
    setState("BROWSER_UNSUPPORTED", "This browser cannot share location, so this portfolio cannot be opened here.", true);
    report("unsupported");
    button.disabled = true;
    return;
  }
  setState("PERMISSION_REQUIRED", "");
  if (navigator.permissions && navigator.permissions.query) {
    navigator.permissions.query({ name: "geolocation" }).then(function (result) {
      if (result.state === "denied") {
        setState("PERMISSION_DENIED", "Location permission is already blocked for this site. Allow it in the browser settings, then try again.", true);
      }
    }).catch(function () {});
  }
})();

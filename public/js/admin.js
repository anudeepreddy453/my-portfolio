(function () {
  var panels = document.querySelectorAll(".panel");
  var buttons = document.querySelectorAll(".nav [data-panel]");
  var charts = {};
  var recordState = { page: 1, sort: "last_seen", dir: "desc" };
  var liveTimer;
  var current = "overview";
  var zone = "Asia/Kolkata";
  var liveQuery = "";
  var liveDevice = "";
  var liveRows = [];
  var liveMeta = { disclaimer: "", window_seconds: 120 };
  var motion = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var copy = {
    overview: "Monitor your website traffic and visitor activity.",
    live: "Sessions with activity in the current live window.",
    records: "Search stored visits. Coordinates open in Google Maps.",
    settings: "Retention, storage, and the privacy notice."
  };

  function el(tag, text, className) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function icon(name) {
    var node = document.createElement("i");
    node.setAttribute("data-lucide", name);
    return node;
  }

  function paint() {
    if (window.lucide) window.lucide.createIcons();
  }

  function when(value) {
    if (!value) return "Unavailable";
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("en-IN", { timeZone: zone });
  }

  function duration(seconds) {
    if (seconds == null || Number.isNaN(Number(seconds))) return "Unavailable";
    var total = Math.max(0, Math.round(Number(seconds)));
    var minutes = Math.floor(total / 60);
    var hours = Math.floor(minutes / 60);
    if (hours) return hours + "h " + (minutes % 60) + "m";
    if (minutes) return minutes + "m " + (total % 60) + "s";
    return total + "s";
  }

  function api(path, options) {
    options = options || {};
    options.headers = options.headers || {};
    options.headers["X-Requested-With"] = "fetch";
    return fetch(path, options).then(function (response) {
      if (response.status === 401) {
        window.location.href = "/admin/login";
        throw new Error("auth");
      }
      if (!response.ok) throw new Error("Request failed");
      var type = response.headers.get("content-type") || "";
      if (type.indexOf("application/json") !== -1) return response.json();
      return response.text();
    });
  }

  function tick() {
    var clock = document.getElementById("clock");
    if (!clock) return;
    clock.textContent = new Date().toLocaleString("en-IN", {
      timeZone: zone,
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "numeric",
      minute: "2-digit"
    });
    clock.dateTime = new Date().toISOString();
  }

  function setLive(active) {
    var pill = document.getElementById("live-pill");
    var label = document.getElementById("live-label");
    if (!pill || !label) return;
    pill.classList.toggle("is-live", active > 0);
    label.textContent = active > 0 ? active + " live" : "Quiet";
  }

  function showStorage(storage) {
    var banner = document.getElementById("storage-banner");
    if (!banner || !storage || !storage.ephemeral) return;
    if (window.sessionStorage.getItem("pv-storage-dismissed") === "1") return;
    document.getElementById("storage-text").textContent = storage.detail;
    banner.hidden = false;
    paint();
  }

  function show(name) {
    current = name;
    buttons.forEach(function (button) {
      var on = button.dataset.panel === name;
      button.classList.toggle("is-active", on);
      if (on) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    panels.forEach(function (panel) {
      panel.hidden = panel.id !== "panel-" + name;
    });
    document.getElementById("page-title").textContent = document.querySelector('.nav [data-panel="' + name + '"] span').textContent;
    document.getElementById("page-copy").textContent = copy[name];
    window.clearInterval(liveTimer);
    if (name === "overview") loadOverview();
    if (name === "live") {
      loadLive();
      liveTimer = window.setInterval(loadLive, 20000);
    }
    if (name === "records") loadRecords();
    if (name === "settings") loadSettings();
  }

  buttons.forEach(function (button) {
    button.addEventListener("click", function () { show(button.dataset.panel); });
  });

  function signOut() {
    api("/admin/logout", { method: "POST" }).then(function () {
      window.location.href = "/admin/login";
    });
  }

  document.getElementById("logout").addEventListener("click", signOut);
  document.getElementById("logout-mobile").addEventListener("click", signOut);
  document.getElementById("refresh").addEventListener("click", function () { show(current); });
  document.getElementById("storage-dismiss").addEventListener("click", function () {
    window.sessionStorage.setItem("pv-storage-dismissed", "1");
    document.getElementById("storage-banner").hidden = true;
  });

  function skeleton(root, count) {
    clear(root);
    var grid = el("div", null, "metrics");
    for (var i = 0; i < count; i += 1) grid.appendChild(el("div", null, "skeleton"));
    root.appendChild(grid);
  }

  function writeNumber(node, value) {
    if (!motion || typeof value !== "number" || !Number.isFinite(value)) {
      node.textContent = value == null || value === "" ? "Unavailable" : String(value);
      return;
    }
    var start = performance.now();
    function frame(now) {
      var progress = Math.min((now - start) / 420, 1);
      node.textContent = String(Math.round(value * progress));
      if (progress < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  function metric(label, value, glyph) {
    var node = el("article", null, "metric glass-panel");
    var top = el("div", null, "metric-top");
    top.appendChild(icon(glyph));
    top.appendChild(el("span", label));
    node.appendChild(top);
    var strong = el("strong");
    node.appendChild(strong);
    writeNumber(strong, value == null ? "Unavailable" : value);
    return node;
  }

  function emptyState(title, detail) {
    var node = el("div", null, "empty");
    node.appendChild(el("strong", title));
    node.appendChild(el("p", detail));
    return node;
  }

  function rankList(rows, labelKey, emptyTitle) {
    if (!rows || !rows.length) return emptyState(emptyTitle, "Nothing has been recorded for this view yet.");
    var max = Math.max.apply(null, rows.map(function (row) { return row.count || row.views || 0; })) || 1;
    var list = el("div", null, "rank");
    rows.forEach(function (row) {
      var count = row.count != null ? row.count : row.views;
      var line = el("div", null, "rank-row");
      line.appendChild(el("span", row[labelKey]));
      line.appendChild(el("b", String(count)));
      var bar = el("div", null, "bar");
      var fill = document.createElement("i");
      fill.style.width = Math.max(6, Math.round((count / max) * 100)) + "%";
      bar.appendChild(fill);
      line.appendChild(bar);
      list.appendChild(line);
    });
    return list;
  }

  function section(title, note) {
    var node = el("section", null, "group");
    var head = el("div", null, "group-head");
    head.appendChild(el("h2", title));
    if (note) head.appendChild(el("p", note));
    node.appendChild(head);
    return node;
  }

  function loadOverview() {
    var root = document.getElementById("panel-overview");
    skeleton(root, 4);
    Promise.all([
      api("/admin/api/overview"),
      api("/admin/api/devices").catch(function () { return null; })
    ]).then(function (results) {
      var data = results[0];
      var devices = results[1];
      zone = data.timezone || zone;
      tick();
      showStorage(data.storage);
      setLive((data.totals || {}).active_sessions || 0);
      copy.live = "Sessions with activity in the last " + Math.round(data.live_window_seconds / 60) + " minutes.";
      if (current === "overview") document.getElementById("page-copy").textContent = "Times use " + zone + ". " + copy.overview;
      clear(root);
      var totals = data.totals || {};
      var audience = section("Audience");
      var cards = el("div", null, "metrics");
      [
        ["Total visits", totals.visits, "bar-chart-3"],
        ["Unique visitors", totals.unique_visitors, "users"],
        ["Today", totals.today, "sun"],
        ["Last 7 days", totals.last_7_days, "calendar"],
        ["Last 30 days", totals.last_30_days, "calendar-range"],
        ["Returning visitors", totals.returning, "repeat"],
        ["New today", totals.new_today, "user-plus"]
      ].forEach(function (item) { cards.appendChild(metric(item[0], item[1], item[2])); });
      audience.appendChild(cards);
      root.appendChild(audience);

      var activity = section("Sessions and location");
      var lower = el("div", null, "metrics");
      [
        ["GPS locations stored", totals.gps_stored, "map-pin"],
        ["Permission denied", totals.gps_denied, "shield-off"],
        ["Active sessions", totals.active_sessions, "radio"],
        ["Average session", duration(totals.avg_duration_seconds), "timer"]
      ].forEach(function (item) { lower.appendChild(metric(item[0], item[1], item[2])); });
      activity.appendChild(lower);
      root.appendChild(activity);

      var chartsRow = el("div", null, "split");
      var visits = el("article", null, "panel-card glass-panel");
      visits.appendChild(el("h2", "Visits"));
      var canvas = el("canvas");
      visits.appendChild(canvas);
      chartsRow.appendChild(visits);
      var mix = el("article", null, "panel-card glass-panel");
      mix.appendChild(el("h2", "Devices"));
      var doughnut = el("canvas");
      mix.appendChild(doughnut);
      chartsRow.appendChild(mix);
      root.appendChild(chartsRow);

      var places = el("div", null, "triple");
      places.appendChild(panelList("Top pages", rankList(data.pages || [], "path", "No page views yet")));
      places.appendChild(panelList("IP countries", rankList(data.countries || [], "name", "No country estimates yet")));
      places.appendChild(panelList("IP cities", rankList(data.cities || [], "name", "No city estimates yet")));
      root.appendChild(places);

      var insight = el("div", null, "split");
      insight.appendChild(panelList("Browsers", rankList(devices && devices.browsers, "name", "No browser data yet")));
      insight.appendChild(panelList("Systems", rankList(devices && devices.systems, "name", "No system data yet")));
      root.appendChild(insight);

      var permissions = data.permissions || {};
      var names = Object.keys(permissions);
      var permissionRows = names.map(function (name) { return { name: name, count: permissions[name] }; });
      root.appendChild(panelList("Location permission events", rankList(permissionRows, "name", "No permission events yet")));
      root.appendChild(el("p", data.disclaimer, "note"));
      drawVisits(canvas, data.series || []);
      drawDevices(doughnut, data.devices || []);
      paint();
    }).catch(function () {
      clear(root);
      root.appendChild(el("p", "Overview could not be loaded.", "error"));
    });
  }

  function panelList(title, body) {
    var card = el("article", null, "panel-card glass-panel");
    card.appendChild(el("h2", title));
    card.appendChild(body);
    return card;
  }

  function drawVisits(canvas, series) {
    if (!window.Chart) return;
    if (charts.visits) charts.visits.destroy();
    var labels = series.map(function (row) {
      var parts = String(row.day).split("-");
      var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      return months[Number(parts[1]) - 1] + " " + Number(parts[2]);
    });
    charts.visits = new window.Chart(canvas, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Visits",
            data: series.map(function (row) { return row.visits; }),
            borderColor: "#8ab4f8",
            backgroundColor: "rgba(138,180,248,0.16)",
            fill: true,
            tension: 0.35,
            pointRadius: 2,
            borderWidth: 2
          },
          {
            label: "Unique visitors",
            data: series.map(function (row) { return row.uniques; }),
            borderColor: "#d8bd91",
            backgroundColor: "transparent",
            tension: 0.35,
            pointRadius: 2,
            borderWidth: 2
          }
        ]
      },
      options: {
        animation: motion ? { duration: 500 } : false,
        plugins: { legend: { labels: { color: "#989ba5", boxWidth: 10 } } },
        scales: {
          x: { ticks: { color: "#989ba5", maxRotation: 0, autoSkip: true }, grid: { color: "rgba(255,255,255,0.04)" } },
          y: { ticks: { color: "#989ba5", precision: 0 }, grid: { color: "rgba(255,255,255,0.04)" }, beginAtZero: true }
        }
      }
    });
  }

  function drawDevices(canvas, rows) {
    if (!window.Chart) return;
    if (charts.devices) charts.devices.destroy();
    var palette = ["#8ab4f8", "#d8bd91", "#8fcead", "#e2c07a", "#e3a39a", "#b7bcc8"];
    charts.devices = new window.Chart(canvas, {
      type: "doughnut",
      data: {
        labels: rows.map(function (row) { return row.name; }),
        datasets: [{
          data: rows.map(function (row) { return row.count; }),
          backgroundColor: rows.map(function (_, index) { return palette[index % palette.length]; }),
          borderWidth: 0
        }]
      },
      options: {
        cutout: "68%",
        animation: motion ? { duration: 500 } : false,
        plugins: { legend: { position: "bottom", labels: { color: "#989ba5", boxWidth: 10 } } }
      }
    });
  }

  function mapsLink(url, label) {
    if (!url) return "Unavailable";
    var link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = label || url;
    link.addEventListener("click", function (event) { event.stopPropagation(); });
    return link;
  }

  function coordinateLink(latitude, longitude, url) {
    if (latitude == null || longitude == null) return "Unavailable";
    return mapsLink(url, latitude + ", " + longitude);
  }

  function renderLive() {
    var root = document.getElementById("panel-live");
    var filtered = liveRows.filter(function (row) {
      var hay = [row.visitor_id, row.ip_address, row.ip_city, row.ip_country, row.current_page, row.browser, row.os].join(" ").toLowerCase();
      var queryOk = !liveQuery || hay.indexOf(liveQuery.toLowerCase()) !== -1;
      var deviceOk = !liveDevice || row.device === liveDevice;
      return queryOk && deviceOk;
    });
    var host = document.getElementById("live-results");
    if (!host) {
      clear(root);
      var tools = el("div", null, "filters");
      var query = el("input");
      query.id = "live-q";
      query.placeholder = "Search visitor, place, page";
      query.value = liveQuery;
      query.addEventListener("input", function () {
        liveQuery = query.value;
        renderLive();
      });
      tools.appendChild(query);
      var selectNode = el("select");
      selectNode.id = "live-device";
      selectNode.addEventListener("change", function () {
        liveDevice = selectNode.value;
        renderLive();
      });
      tools.appendChild(selectNode);
      root.appendChild(tools);
      root.appendChild(el("p", liveMeta.disclaimer || "", "note"));
      host = el("div");
      host.id = "live-results";
      root.appendChild(host);
    }
    var selectNode = document.getElementById("live-device");
    var chosen = liveDevice;
    clear(selectNode);
    selectNode.appendChild(el("option", "All devices"));
    selectNode.firstChild.value = "";
    var devices = [];
    liveRows.forEach(function (row) { if (devices.indexOf(row.device) === -1) devices.push(row.device); });
    devices.forEach(function (name) {
      var option = el("option", name);
      option.value = name;
      selectNode.appendChild(option);
    });
    selectNode.value = devices.indexOf(chosen) === -1 ? "" : chosen;
    clear(host);
    host.appendChild(table(
      ["Visitor", "Page", "IP", "IP city", "IP country", "Coordinates", "GPS", "Device", "Browser", "System", "First seen", "Last active", "Duration"],
      filtered.map(function (row) {
        return [row.visitor_id, row.current_page, row.ip_address, row.ip_city, row.ip_country, coordinateLink(row.latitude, row.longitude, row.maps_url), row.gps_status, row.device, row.browser, row.os, when(row.first_seen), when(row.last_active), duration(row.duration_seconds)];
      }),
      filtered.length ? "No active sessions." : (liveRows.length ? "No sessions match this search." : "No active sessions.")
    ));
    paint();
  }

  function loadLive() {
    var root = document.getElementById("panel-live");
    if (!root.childElementCount) skeleton(root, 2);
    api("/admin/api/live").then(function (data) {
      liveRows = data.visitors || [];
      liveMeta = data;
      setLive(liveRows.length);
      copy.live = "Shown only when activity arrived in the last " + Math.round(data.window_seconds / 60) + " minutes.";
      if (current === "live") document.getElementById("page-copy").textContent = copy.live;
      if (document.getElementById("live-results")) {
        var note = root.querySelector(".note");
        if (note) note.textContent = data.disclaimer || "";
      } else if (root.querySelector(".skeleton")) {
        clear(root);
      }
      renderLive();
    });
  }

  function addLine(list, label, value) {
    list.appendChild(el("dt", label));
    var dd = el("dd");
    if (value && value.nodeType) dd.appendChild(value);
    else dd.textContent = value == null || value === "" ? "Unavailable" : String(value);
    list.appendChild(dd);
  }

  function factCard(title, pairs) {
    var card = el("article", null, "panel-card glass-panel");
    card.appendChild(el("h2", title));
    var list = el("dl", null, "facts");
    pairs.forEach(function (pair) { addLine(list, pair[0], pair[1]); });
    card.appendChild(list);
    return card;
  }

  function loadRecords() {
    var params = new URLSearchParams();
    var form = document.getElementById("record-filters");
    if (form) {
      new FormData(form).forEach(function (value, key) {
        if (value) params.set(key, value);
      });
    }
    params.set("page", String(recordState.page));
    params.set("sort", recordState.sort);
    params.set("dir", recordState.dir);
    var root = document.getElementById("panel-records");
    api("/admin/api/visitors?" + params.toString()).then(function (data) {
      var existing = document.getElementById("record-filters");
      var remembered = existing ? new FormData(existing) : null;
      clear(root);
      var head = el("div", null, "toolbar");
      var exportButton = el("button", "Export CSV", "primary");
      exportButton.type = "button";
      exportButton.addEventListener("click", exportCsv);
      head.appendChild(exportButton);
      root.appendChild(head);
      root.appendChild(filterForm(data.facets || {}, remembered));
      root.appendChild(table(
        ["Visitor", "IP", "IP country", "IP city", "Device", "Browser", "Coordinates", "First visit", "Last visit", "Visits"],
        (data.rows || []).map(function (row) {
          return [row.visitor_id, row.ip_address, row.ip_country, row.ip_city, row.device, row.browser, coordinateLink(row.latitude, row.longitude, row.maps_url), when(row.first_visit), when(row.last_visit), row.visit_count];
        }),
        "No visitors match these filters.",
        (data.rows || []).map(function (row) { return row.visitor_id; })
      ));
      var pager = el("div", null, "pager");
      var prev = el("button", "Previous", "ghost");
      var next = el("button", "Next", "ghost");
      prev.type = "button";
      next.type = "button";
      prev.disabled = data.page <= 1;
      next.disabled = data.page * data.page_size >= data.total;
      prev.addEventListener("click", function () { recordState.page -= 1; loadRecords(); });
      next.addEventListener("click", function () { recordState.page += 1; loadRecords(); });
      pager.appendChild(prev);
      pager.appendChild(el("span", data.total + " records"));
      pager.appendChild(next);
      root.appendChild(pager);
      paint();
    });
  }

  function filterForm(facets, remembered) {
    var form = el("form", null, "filters");
    form.id = "record-filters";
    function field(name, placeholder, type) {
      var input = el("input");
      input.name = name;
      input.placeholder = placeholder;
      if (type) input.type = type;
      if (remembered && remembered.get(name)) input.value = remembered.get(name);
      return input;
    }
    form.appendChild(field("q", "Search id, IP, city"));
    form.appendChild(field("city", "IP city"));
    form.appendChild(selectBox("country", "IP country", facets.countries || [], remembered));
    form.appendChild(selectBox("device", "Device", facets.devices || [], remembered));
    form.appendChild(selectBox("gps", "GPS", ["granted", "denied", "none"], remembered));
    form.appendChild(field("from", "", "date"));
    form.appendChild(field("to", "", "date"));
    var submit = el("button", "Filter", "primary");
    submit.type = "submit";
    form.appendChild(submit);
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      recordState.page = 1;
      loadRecords();
    });
    return form;
  }

  function selectBox(name, label, options, remembered) {
    var node = el("select");
    node.name = name;
    node.appendChild(el("option", label));
    node.firstChild.value = "";
    options.forEach(function (option) {
      var item = el("option", option);
      item.value = option;
      node.appendChild(item);
    });
    if (remembered && remembered.get(name)) node.value = remembered.get(name);
    return node;
  }

  function table(headers, rows, empty, ids) {
    var wrap = el("div", null, "table-wrap glass-panel");
    if (!rows.length) {
      wrap.appendChild(emptyState(empty, "Try another filter, or wait for a new visit."));
      return wrap;
    }
    var tableNode = el("table");
    var thead = el("thead");
    var headRow = el("tr");
    headers.forEach(function (header) { headRow.appendChild(el("th", header)); });
    thead.appendChild(headRow);
    tableNode.appendChild(thead);
    var body = el("tbody");
    rows.forEach(function (row, index) {
      var tr = el("tr");
      if (ids && ids[index]) {
        tr.dataset.id = ids[index];
        tr.addEventListener("click", function () { loadDetail(ids[index]); });
      }
      row.forEach(function (value, cellIndex) {
        var cell = el("td");
        cell.dataset.label = headers[cellIndex];
        if (value && value.nodeType) cell.appendChild(value);
        else cell.textContent = value == null ? "" : String(value);
        tr.appendChild(cell);
      });
      body.appendChild(tr);
    });
    tableNode.appendChild(body);
    wrap.appendChild(tableNode);
    return wrap;
  }

  function loadDetail(visitorId) {
    var root = document.getElementById("panel-records");
    skeleton(root, 2);
    api("/admin/api/visitors/" + encodeURIComponent(visitorId)).then(function (data) {
      clear(root);
      var head = el("div", null, "toolbar");
      var back = el("button", "Back to records", "ghost");
      back.type = "button";
      back.addEventListener("click", loadRecords);
      head.appendChild(back);
      head.appendChild(actionButton("Delete GPS coordinates", function () {
        if (!window.confirm("Delete stored GPS coordinates for this visitor?")) return;
        api("/admin/api/visitors/" + encodeURIComponent(visitorId) + "/delete-gps", { method: "POST" }).then(function () { loadDetail(visitorId); });
      }, "danger"));
      head.appendChild(actionButton("Delete visitor record", function () {
        if (!window.confirm("Delete this visitor and their sessions?")) return;
        api("/admin/api/visitors/" + encodeURIComponent(visitorId) + "/delete", { method: "POST" }).then(loadRecords);
      }, "danger"));
      root.appendChild(head);
      root.appendChild(el("p", "Visits " + data.visit_count + " · First " + when(data.first_seen_at) + " · Last " + when(data.last_seen_at)));
      root.appendChild(el("p", data.disclaimer, "note"));
      (data.sessions || []).forEach(function (session) {
        var grid = el("div", null, "stack");
        grid.appendChild(factCard("Session " + session.session_id, [
          ["Access", session.access_status],
          ["Consent", session.consent_status],
          ["Started", when(session.started_at)],
          ["Last active", when(session.last_activity_at)],
          ["Duration", duration(session.duration_seconds)],
          ["Entry", session.entry_page || "Unavailable"],
          ["Exit", session.exit_page || "Unavailable"],
          ["Referrer", session.referrer || "Direct"]
        ]));
        if (session.ip) {
          grid.appendChild(factCard(session.ip.source_label, [
            ["IP", session.ip.ip_address],
            ["Version", session.ip.ip_version || "Unavailable"],
            ["City", session.ip.city || "Unavailable"],
            ["Region", session.ip.region || "Unavailable"],
            ["Country", session.ip.country || "Unavailable"],
            ["ISP", session.ip.isp || "Unavailable"],
            ["ASN", session.ip.asn || "Unavailable"],
            ["Estimated coordinates", coordinateLink(session.ip.latitude, session.ip.longitude, session.ip.maps_url)]
          ]));
        }
        if (session.gps) {
          grid.appendChild(factCard(session.gps.source_label, [
            ["Coordinates", coordinateLink(session.gps.latitude, session.gps.longitude, session.gps.maps_url)],
            ["Accuracy", session.gps.accuracy_m == null ? "Unavailable" : session.gps.accuracy_m + " m"],
            ["Captured", when(session.gps.captured_at)],
            ["Device time", when(session.gps.position_at)]
          ]));
        }
        if (session.device) {
          grid.appendChild(factCard("Device", [
            ["Type", session.device.device_type || "Unavailable"],
            ["Model", session.device.device_model || "Unavailable"],
            ["Browser", (session.device.browser || "Unavailable") + (session.device.browser_version ? " " + session.device.browser_version : "")],
            ["System", (session.device.os_name || "Unavailable") + (session.device.os_version ? " " + session.device.os_version : "")],
            ["Language", session.device.language || "Unavailable"],
            ["Time zone", session.device.timezone || "Unavailable"],
            ["Screen", session.device.screen_resolution || "Unavailable"],
            ["Viewport", session.device.viewport || "Unavailable"]
          ]));
        }
        var pages = el("article", null, "panel-card glass-panel");
        pages.appendChild(el("h2", "Pages"));
        if (session.pages && session.pages.length) {
          session.pages.forEach(function (page) {
            pages.appendChild(el("p", when(page.occurred_at) + " · " + page.page_path));
          });
        } else {
          pages.appendChild(emptyState("No page views yet", "A page view is recorded after the portfolio opens."));
        }
        grid.appendChild(pages);
        var revoke = actionButton("Revoke session", function () {
          if (!window.confirm("Revoke this session? The visitor will need to allow location again.")) return;
          api("/admin/api/sessions/" + encodeURIComponent(session.session_id) + "/revoke", { method: "POST" }).then(function () { loadDetail(visitorId); });
        }, "danger");
        grid.appendChild(revoke);
        root.appendChild(grid);
      });
      paint();
    });
  }

  function actionButton(label, onClick, className) {
    var button = el("button", label, className || "primary");
    button.type = "button";
    button.addEventListener("click", onClick);
    return button;
  }

  function settingGroup(title, text) {
    var card = el("article", null, "panel-card glass-panel");
    card.appendChild(el("h2", title));
    if (text) card.appendChild(el("p", text, "note"));
    return card;
  }

  function loadSettings() {
    var root = document.getElementById("panel-settings");
    skeleton(root, 2);
    api("/admin/api/settings").then(function (data) {
      zone = data.timezone || zone;
      clear(root);
      var retention = settingGroup("Data retention", "GPS and IP coordinates, then session history, are removed after these periods.");
      var form = el("form", null, "stack");
      form.appendChild(el("label", "GPS and IP coordinate retention (days)"));
      var gps = el("input");
      gps.name = "gps_retention_days";
      gps.type = "number";
      gps.min = "1";
      gps.max = "3650";
      gps.value = data.gps_retention_days;
      form.lastChild.appendChild(gps);
      form.appendChild(el("label", "Session history retention (days)"));
      var activity = el("input");
      activity.name = "activity_retention_days";
      activity.type = "number";
      activity.min = "1";
      activity.max = "3650";
      activity.value = data.activity_retention_days;
      form.lastChild.appendChild(activity);
      var save = el("button", "Save retention", "primary");
      save.type = "submit";
      form.appendChild(save);
      var message = el("p", "", "muted");
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        api("/admin/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            gps_retention_days: Number(gps.value),
            activity_retention_days: Number(activity.value)
          })
        }).then(function () {
          message.className = "ok";
          message.textContent = "Retention saved.";
        }).catch(function () {
          message.className = "error";
          message.textContent = "Could not save retention.";
        });
      });
      form.appendChild(message);
      retention.appendChild(form);
      root.appendChild(retention);

      root.appendChild(settingGroup(
        "Visitor tracking",
        "A granted visit stays open for " + data.session_hours + " hours. That duration is set with VISITOR_SESSION_HOURS. Privacy notice " + data.notice_version + ". Time zone " + data.timezone + "."
      ));
      root.appendChild(settingGroup("Database and storage", data.storage.detail));
      root.appendChild(settingGroup(
        "Security",
        "Admin sign-in uses the password in VISITOR_ADMIN_PASSWORD. This screen cannot change that password."
      ));
      paint();
    });
  }

  function exportCsv() {
    api("/admin/api/export", { method: "POST" }).then(function (text) {
      var blob = new Blob([text], { type: "text/csv" });
      var link = el("a");
      link.href = URL.createObjectURL(blob);
      link.download = "visitor-records.csv";
      link.click();
      URL.revokeObjectURL(link.href);
    });
  }

  tick();
  window.setInterval(tick, 30000);
  paint();
  show("overview");
})();

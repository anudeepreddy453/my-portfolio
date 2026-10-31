(function () {
  var panels = document.querySelectorAll(".panel");
  var buttons = document.querySelectorAll(".nav [data-panel]");
  var charts = {};
  var recordState = { page: 1, sort: "last_seen", dir: "desc" };
  var liveTimer;

  function el(tag, text, className) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function when(value) {
    if (!value) return "Unavailable";
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString();
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

  function show(name) {
    buttons.forEach(function (button) {
      button.classList.toggle("is-active", button.dataset.panel === name);
    });
    panels.forEach(function (panel) {
      panel.hidden = panel.id !== "panel-" + name;
    });
    window.clearInterval(liveTimer);
    if (name === "overview") loadOverview();
    if (name === "live") {
      loadLive();
      liveTimer = window.setInterval(loadLive, 20000);
    }
    if (name === "records") loadRecords();
    if (name === "devices") loadDevices();
    if (name === "sources") loadSources();
    if (name === "permissions") loadPermissions();
    if (name === "settings") loadSettings();
  }

  buttons.forEach(function (button) {
    button.addEventListener("click", function () { show(button.dataset.panel); });
  });

  document.getElementById("logout").addEventListener("click", function () {
    api("/admin/logout", { method: "POST" }).then(function () {
      window.location.href = "/admin/login";
    });
  });

  function card(label, value) {
    var node = el("article", null, "card");
    node.appendChild(el("span", label));
    node.appendChild(el("strong", value));
    return node;
  }

  function loadOverview() {
    api("/admin/api/overview").then(function (data) {
      var banner = document.getElementById("storage-banner");
      if (data.storage && data.storage.ephemeral) {
        banner.hidden = false;
        banner.textContent = data.storage.detail;
      }
      var root = document.getElementById("panel-overview");
      clear(root);
      var head = el("header", null, "panel-head");
      head.appendChild(el("h1", "Overview"));
      head.appendChild(el("p", "Times use " + data.timezone + ". Live means activity in the last " + Math.round(data.live_window_seconds / 60) + " minutes.", "muted"));
      root.appendChild(head);
      var totals = data.totals || {};
      var cards = el("div", null, "cards");
      [
        ["Total visits", totals.visits],
        ["Unique visitors", totals.unique_visitors],
        ["Today", totals.today],
        ["Last 7 days", totals.last_7_days],
        ["Last 30 days", totals.last_30_days],
        ["Returning", totals.returning],
        ["New today", totals.new_today],
        ["GPS locations stored", totals.gps_stored],
        ["Permission denied", totals.gps_denied],
        ["Active sessions", totals.active_sessions],
        ["Average session", duration(totals.avg_duration_seconds)]
      ].forEach(function (item) { cards.appendChild(card(item[0], item[1])); });
      root.appendChild(cards);
      var split = el("div", null, "split");
      var chartCard = el("article", null, "card");
      chartCard.appendChild(el("h2", "Visits"));
      var canvas = el("canvas");
      chartCard.appendChild(canvas);
      split.appendChild(chartCard);
      var side = el("article", null, "card");
      side.appendChild(el("h2", "Top pages"));
      (data.pages || []).forEach(function (row) {
        var line = el("p");
        line.appendChild(el("strong", row.views + " · "));
        line.appendChild(document.createTextNode(row.path));
        side.appendChild(line);
      });
      if (!data.pages || !data.pages.length) side.appendChild(el("p", "No page views yet.", "muted"));
      side.appendChild(el("h2", "IP countries"));
      (data.countries || []).forEach(function (row) {
        side.appendChild(el("p", row.count + " · " + row.name));
      });
      side.appendChild(el("h2", "IP cities"));
      (data.cities || []).forEach(function (row) {
        side.appendChild(el("p", row.count + " · " + row.name));
      });
      split.appendChild(side);
      root.appendChild(split);
      root.appendChild(el("p", data.disclaimer, "note"));
      drawChart(canvas, (data.series || []).map(function (row) { return row.day.slice(5); }), (data.series || []).map(function (row) { return row.visits; }), "Visits");
    }).catch(function () {
      document.getElementById("panel-overview").appendChild(el("p", "Overview could not be loaded.", "error"));
    });
  }

  function drawChart(canvas, labels, values, label) {
    if (!window.Chart) {
      canvas.replaceWith(el("p", "Charts could not be loaded.", "muted"));
      return;
    }
    if (charts[label]) charts[label].destroy();
    charts[label] = new window.Chart(canvas, {
      type: "bar",
      data: { labels: labels, datasets: [{ label: label, data: values, backgroundColor: "rgba(226,196,138,0.75)", borderRadius: 6 }] },
      options: {
        plugins: { legend: { labels: { color: "#f6f3ec" } } },
        scales: {
          x: { ticks: { color: "#b7b1a6" }, grid: { color: "rgba(255,255,255,0.05)" } },
          y: { ticks: { color: "#b7b1a6", precision: 0 }, grid: { color: "rgba(255,255,255,0.05)" }, beginAtZero: true }
        }
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

  function loadLive() {
    api("/admin/api/live").then(function (data) {
      var root = document.getElementById("panel-live");
      clear(root);
      var head = el("header", null, "panel-head");
      head.appendChild(el("h1", "Live visitors"));
      head.appendChild(el("p", "Shown only when activity arrived in the last " + Math.round(data.window_seconds / 60) + " minutes. Click coordinates to open Google Maps.", "muted"));
      root.appendChild(head);
      root.appendChild(el("p", data.disclaimer, "note"));
      root.appendChild(table(
        ["Visitor", "Page", "IP", "IP city", "IP country", "Coordinates", "Device", "Browser", "First seen", "Last active", "Duration"],
        (data.visitors || []).map(function (row) {
          return [row.visitor_id, row.current_page, row.ip_address, row.ip_city, row.ip_country, coordinateLink(row.latitude, row.longitude, row.maps_url), row.device, row.browser, when(row.first_seen), when(row.last_active), duration(row.duration_seconds)];
        }),
        "No active sessions."
      ));
    });
  }

  function addLine(parent, label, value) {
    var line = el("p");
    line.appendChild(el("strong", label + ": "));
    if (value && value.nodeType) line.appendChild(value);
    else line.appendChild(document.createTextNode(value == null || value === "" ? "Unavailable" : String(value)));
    parent.appendChild(line);
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
    api("/admin/api/visitors?" + params.toString()).then(function (data) {
      var root = document.getElementById("panel-records");
      var existing = document.getElementById("record-filters");
      var remembered = existing ? new FormData(existing) : null;
      clear(root);
      var head = el("header", null, "panel-head");
      head.appendChild(el("h1", "Visitor records"));
      var exportButton = el("button", "Export CSV", "primary");
      exportButton.type = "button";
      exportButton.addEventListener("click", exportCsv);
      head.appendChild(exportButton);
      root.appendChild(head);
      root.appendChild(el("p", "Click a coordinate to open that point in Google Maps.", "muted"));
      root.appendChild(filterForm(data.facets || {}, remembered));
      var wrap = table(
        ["Visitor", "IP", "IP country", "IP city", "Device", "Browser", "Coordinates", "First visit", "Last visit", "Visits"],
        (data.rows || []).map(function (row) {
          return [row.visitor_id, row.ip_address, row.ip_country, row.ip_city, row.device, row.browser, coordinateLink(row.latitude, row.longitude, row.maps_url), when(row.first_visit), when(row.last_visit), row.visit_count];
        }),
        "No visitors match these filters.",
        (data.rows || []).map(function (row) { return row.visitor_id; })
      );
      root.appendChild(wrap);
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
    });
  }

  function filterForm(facets, remembered) {
    var form = el("form", null, "toolbar");
    form.id = "record-filters";
    function field(name, placeholder) {
      var input = el("input");
      input.name = name;
      input.placeholder = placeholder;
      if (remembered && remembered.get(name)) input.value = remembered.get(name);
      return input;
    }
    form.appendChild(field("q", "Search id, IP, city"));
    form.appendChild(field("city", "IP city"));
    form.appendChild(select("country", "IP country", facets.countries || [], remembered));
    form.appendChild(select("device", "Device", facets.devices || [], remembered));
    var gps = select("gps", "GPS", ["granted", "denied", "none"], remembered);
    form.appendChild(gps);
    var from = field("from", "");
    from.type = "date";
    var to = field("to", "");
    to.type = "date";
    form.appendChild(from);
    form.appendChild(to);
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

  function select(name, label, options, remembered) {
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
    var wrap = el("div", null, "table-wrap");
    if (!rows.length) {
      wrap.appendChild(el("p", empty, "muted"));
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
      row.forEach(function (value) {
        var cell = el("td");
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
    api("/admin/api/visitors/" + encodeURIComponent(visitorId)).then(function (data) {
      var root = document.getElementById("panel-records");
      clear(root);
      var head = el("header", null, "panel-head");
      var back = el("button", "Back to records", "ghost");
      back.type = "button";
      back.addEventListener("click", loadRecords);
      head.appendChild(el("h1", data.visitor_id));
      head.appendChild(back);
      root.appendChild(head);
      root.appendChild(el("p", data.disclaimer, "note"));
      var actions = el("div", null, "toolbar");
      actions.appendChild(actionButton("Delete GPS coordinates", function () {
        if (!window.confirm("Delete stored GPS coordinates for this visitor?")) return;
        api("/admin/api/visitors/" + encodeURIComponent(visitorId) + "/delete-gps", { method: "POST" }).then(function () { loadDetail(visitorId); });
      }, "danger"));
      actions.appendChild(actionButton("Delete visitor record", function () {
        if (!window.confirm("Delete this visitor and their sessions?")) return;
        api("/admin/api/visitors/" + encodeURIComponent(visitorId) + "/delete", { method: "POST" }).then(loadRecords);
      }, "danger"));
      root.appendChild(actions);
      root.appendChild(el("p", "Visits: " + data.visit_count + " · First " + when(data.first_seen_at) + " · Last " + when(data.last_seen_at)));
      (data.sessions || []).forEach(function (session) {
        var cardNode = el("article", null, "card");
        cardNode.style.marginTop = "0.8rem";
        cardNode.appendChild(el("h2", "Session " + session.session_id));
        addLine(cardNode, "Access", session.access_status);
        addLine(cardNode, "Consent", session.consent_status);
        addLine(cardNode, "Started", when(session.started_at));
        addLine(cardNode, "Last active", when(session.last_activity_at));
        addLine(cardNode, "Duration", duration(session.duration_seconds));
        addLine(cardNode, "Entry", session.entry_page || "Unavailable");
        addLine(cardNode, "Exit", session.exit_page || "Unavailable");
        addLine(cardNode, "Referrer", session.referrer || "Direct");
        if (session.ip) {
          cardNode.appendChild(el("h2", session.ip.source_label));
          addLine(cardNode, "IP", session.ip.ip_address);
          addLine(cardNode, "Version", session.ip.ip_version || "Unavailable");
          addLine(cardNode, "City", session.ip.city || "Unavailable");
          addLine(cardNode, "Region", session.ip.region || "Unavailable");
          addLine(cardNode, "Country", session.ip.country || "Unavailable");
          addLine(cardNode, "ISP", session.ip.isp || "Unavailable");
          addLine(cardNode, "ASN", session.ip.asn || "Unavailable");
          addLine(cardNode, "Estimated coordinates", coordinateLink(session.ip.latitude, session.ip.longitude, session.ip.maps_url));
        }
        if (session.gps) {
          cardNode.appendChild(el("h2", session.gps.source_label));
          addLine(cardNode, "Coordinates", coordinateLink(session.gps.latitude, session.gps.longitude, session.gps.maps_url));
          addLine(cardNode, "Accuracy", session.gps.accuracy_m == null ? "Unavailable" : session.gps.accuracy_m + " m");
          addLine(cardNode, "Captured", when(session.gps.captured_at));
          addLine(cardNode, "Device time", when(session.gps.position_at));
        }
        if (session.device) {
          cardNode.appendChild(el("h2", "Device"));
          addLine(cardNode, "Type", session.device.device_type || "Unavailable");
          addLine(cardNode, "Model", session.device.device_model || "Unavailable");
          addLine(cardNode, "Browser", (session.device.browser || "Unavailable") + (session.device.browser_version ? " " + session.device.browser_version : ""));
          addLine(cardNode, "System", (session.device.os_name || "Unavailable") + (session.device.os_version ? " " + session.device.os_version : ""));
          addLine(cardNode, "Language", session.device.language || "Unavailable");
          addLine(cardNode, "Time zone", session.device.timezone || "Unavailable");
          addLine(cardNode, "Screen", session.device.screen_resolution || "Unavailable");
          addLine(cardNode, "Viewport", session.device.viewport || "Unavailable");
        }
        var pages = el("div");
        pages.appendChild(el("h2", "Pages"));
        (session.pages || []).forEach(function (page) {
          pages.appendChild(el("p", when(page.occurred_at) + " · " + page.page_path));
        });
        if (!session.pages || !session.pages.length) pages.appendChild(el("p", "No page views recorded.", "muted"));
        cardNode.appendChild(pages);
        var revoke = actionButton("Revoke session", function () {
          api("/admin/api/sessions/" + encodeURIComponent(session.session_id) + "/revoke", { method: "POST" }).then(function () { loadDetail(visitorId); });
        }, "danger");
        cardNode.appendChild(revoke);
        root.appendChild(cardNode);
      });
    });
  }

  function actionButton(label, onClick, className) {
    var button = el("button", label, className || "primary");
    button.type = "button";
    button.addEventListener("click", onClick);
    return button;
  }

  function loadDevices() {
    api("/admin/api/devices").then(function (data) {
      var root = document.getElementById("panel-devices");
      clear(root);
      root.appendChild(el("h1", "Devices & browsers"));
      root.appendChild(el("h2", "Device type"));
      root.appendChild(simpleList(data.devices));
      root.appendChild(el("h2", "Browsers"));
      root.appendChild(simpleList((data.browsers || []).map(function (row) {
        return { name: row.name + " " + row.version, count: row.count };
      })));
      root.appendChild(el("h2", "Operating systems"));
      root.appendChild(simpleList(data.systems));
    });
  }

  function loadSources() {
    api("/admin/api/sources").then(function (data) {
      var root = document.getElementById("panel-sources");
      clear(root);
      root.appendChild(el("h1", "Traffic sources"));
      root.appendChild(simpleList((data.sources || []).map(function (row) {
        return { name: row.source, count: row.count };
      })));
    });
  }

  function simpleList(rows) {
    var wrap = el("div", null, "card");
    (rows || []).forEach(function (row) {
      wrap.appendChild(el("p", row.count + " · " + row.name));
    });
    if (!rows || !rows.length) wrap.appendChild(el("p", "Nothing recorded yet.", "muted"));
    return wrap;
  }

  function loadPermissions() {
    api("/admin/api/permissions").then(function (data) {
      var root = document.getElementById("panel-permissions");
      clear(root);
      root.appendChild(el("h1", "Location permissions"));
      root.appendChild(el("p", data.note, "note"));
      var cards = el("div", null, "cards");
      Object.keys(data.counts || {}).forEach(function (key) {
        cards.appendChild(card(key + " · " + (data.percents[key] || 0) + "%", data.counts[key]));
      });
      root.appendChild(cards);
      var canvas = el("canvas");
      root.appendChild(canvas);
      drawChart(
        canvas,
        (data.series || []).map(function (row) { return row.day.slice(5); }),
        (data.series || []).map(function (row) { return row.collected; }),
        "Collected"
      );
    });
  }

  function loadSettings() {
    api("/admin/api/settings").then(function (data) {
      var root = document.getElementById("panel-settings");
      clear(root);
      root.appendChild(el("h1", "Settings"));
      root.appendChild(el("p", data.storage.detail, "note"));
      var form = el("form", null, "stack");
      form.appendChild(el("label", "GPS and IP coordinate retention (days)"));
      var gps = el("input");
      gps.name = "gps_retention_days";
      gps.type = "number";
      gps.min = "1";
      gps.max = "3650";
      gps.value = data.gps_retention_days;
      form.appendChild(gps);
      form.appendChild(el("label", "Session history retention (days)"));
      var activity = el("input");
      activity.name = "activity_retention_days";
      activity.type = "number";
      activity.min = "1";
      activity.max = "3650";
      activity.value = data.activity_retention_days;
      form.appendChild(activity);
      form.appendChild(el("p", "A granted visit stays open for " + data.session_hours + " hours. That duration is set with VISITOR_SESSION_HOURS.", "muted"));
      form.appendChild(el("p", "Privacy notice " + data.notice_version + " · timezone " + data.timezone, "muted"));
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
          message.textContent = "Retention saved.";
        }).catch(function () {
          message.textContent = "Could not save retention.";
        });
      });
      root.appendChild(form);
      root.appendChild(message);
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

  show("overview");
})();

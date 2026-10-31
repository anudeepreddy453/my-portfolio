"""HTTP routes for the location gate, analytics beacons, and admin dashboard."""

from __future__ import annotations

import csv
import hmac
import io
import math
import os
import re
from datetime import datetime, timezone

from flask import Blueprint, abort, jsonify, redirect, request, session

from visitor_intel import store
from visitor_intel.access import attach, client_ip, csrf_ok, refresh_session_cookie
from visitor_intel.net import NOTICE_VERSION, clean_label, clean_metric, clean_path

bp = Blueprint("visitor_intel", __name__)

VISITOR_RE = re.compile(r"^v_[a-f0-9]{16}$")
SESSION_RE = re.compile(r"^s_[a-f0-9]{32}$")
OUTCOMES = {"denied", "dismissed", "unavailable", "timeout", "unsupported"}


@bp.before_request
def _prepare_api_session():
    if request.path.startswith("/api/"):
        attach(create=False)


@bp.before_request
def _guard_admin():
    if not request.path.startswith("/admin"):
        return None
    if request.path == "/admin/login":
        return None
    if session.get("admin_ok"):
        return None
    if request.path.startswith("/admin/api"):
        return jsonify({"ok": False, "error": "Sign in required."}), 401
    return redirect("/admin/login")


@bp.route("/privacy")
def privacy():
    from flask import render_template

    return render_template(
        "privacy.html",
        gps_days=store.setting_int("gps_retention_days", 30, 1, 3650),
        activity_days=store.setting_int("activity_retention_days", 90, 1, 3650),
        session_hours=store.session_hours(),
        notice_version=NOTICE_VERSION,
    )


@bp.post("/api/access/location")
def access_location():
    limited = _hit_limit("location", 10, 15 * 60)
    if limited:
        return limited
    row = _session_or_error()
    if not isinstance(row, dict):
        return row
    if not csrf_ok():
        return jsonify({"ok": False, "error": "Reload this page and try again."}), 403
    if row["access_status"] == "revoked":
        return jsonify({"ok": False, "unlocked": False, "error": "This session was revoked."}), 403
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Invalid request."}), 400
    latitude = _coord(payload.get("latitude"), -90, 90)
    longitude = _coord(payload.get("longitude"), -180, 180)
    accuracy = _coord(payload.get("accuracy"), 0, 1_000_000)
    if latitude is None or longitude is None or accuracy is None:
        store.add_permission_event(row["session_key"], "server_rejected")
        return jsonify({"ok": False, "unlocked": False, "error": "Location reading was incomplete."}), 400
    saved = store.store_gps(
        row["session_key"],
        latitude=latitude,
        longitude=longitude,
        accuracy_m=accuracy,
        position_at=_position_time(payload.get("timestamp")),
        device_extra={
            "screen_resolution": clean_metric(payload.get("screen"), pattern=r"\d{2,5}x\d{2,5}"),
            "viewport": clean_metric(payload.get("viewport"), pattern=r"\d{2,5}x\d{2,5}"),
            "language": clean_label(payload.get("language"), 40),
            "timezone": clean_label(payload.get("timezone"), 64),
        },
    )
    if not saved:
        store.add_permission_event(row["session_key"], "server_rejected")
        return jsonify({"ok": False, "unlocked": False, "error": "Location could not be saved."}), 400
    refresh_session_cookie()
    return jsonify({"ok": True, "unlocked": True})


@bp.post("/api/access/outcome")
def access_outcome():
    limited = _hit_limit("outcome", 20, 15 * 60)
    if limited:
        return limited
    row = _session_or_error()
    if not isinstance(row, dict):
        return row
    if not csrf_ok():
        return jsonify({"ok": False, "error": "Reload this page and try again."}), 403
    payload = request.get_json(silent=True) or {}
    status = payload.get("status") if isinstance(payload, dict) else None
    if status not in OUTCOMES:
        return jsonify({"ok": False, "unlocked": False}), 400
    store.record_outcome(row["session_key"], status)
    return jsonify({"ok": True, "unlocked": False})


@bp.post("/api/analytics/page")
def analytics_page():
    row = _granted_analytics()
    if not isinstance(row, dict):
        return row
    if not store.allow_rate(f"page:{row['session_key']}", 60, 3600):
        return jsonify({"ok": True, "skipped": True})
    payload = request.get_json(silent=True) or {}
    path = clean_path(payload.get("path") if isinstance(payload, dict) else "/")
    referrer = clean_label(payload.get("referrer"), 500) if isinstance(payload, dict) else None
    store.touch(row["session_key"], path, event_type="pageview", referrer=referrer)
    return jsonify({"ok": True})


@bp.post("/api/analytics/heartbeat")
def analytics_heartbeat():
    row = _granted_analytics()
    if not isinstance(row, dict):
        return row
    if not store.allow_rate(f"beat:{row['session_key']}", 240, 3600):
        return jsonify({"ok": True, "skipped": True})
    payload = request.get_json(silent=True) or {}
    path = clean_path(payload.get("path") if isinstance(payload, dict) else row.get("current_path") or "/")
    store.touch(row["session_key"], path, event_type="heartbeat")
    return jsonify({"ok": True})


@bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    from flask import render_template

    configured = bool(os.environ.get("VISITOR_ADMIN_PASSWORD"))
    error = ""
    if request.method == "POST":
        ip = client_ip()
        if not store.allow_rate(f"admin-login:{ip or 'unknown'}", 8, 15 * 60):
            error = "Too many sign-in attempts. Wait a few minutes and try again."
        else:
            expected = session.get("login_csrf") or ""
            sent = request.form.get("csrf") or ""
            password = request.form.get("password") or ""
            token_ok = bool(expected and sent) and _secret_match(sent, str(expected))
            password_ok = configured and _secret_match(password, os.environ.get("VISITOR_ADMIN_PASSWORD", ""))
            if token_ok and password_ok:
                session.clear()
                session["admin_ok"] = True
                session.permanent = True
                store.audit("admin_login", None, ip)
                return redirect("/admin")
            error = "That password is not correct." if configured else "Admin password is not configured."
    token = os.urandom(24).hex()
    session["login_csrf"] = token
    return render_template("admin/login.html", csrf_token=token, error=error, configured=configured)


@bp.post("/admin/logout")
def admin_logout():
    if request.headers.get("X-Requested-With") != "fetch" or not _same_origin():
        abort(403)
    store.audit("admin_logout", None, client_ip())
    session.clear()
    return jsonify({"ok": True})


@bp.get("/admin")
def admin_home():
    from flask import render_template

    return render_template("admin/dashboard.html")


@bp.get("/admin/api/overview")
def admin_overview():
    return jsonify(store.overview())


@bp.get("/admin/api/live")
def admin_live():
    return jsonify({"window_seconds": store.LIVE_WINDOW_SECONDS, "visitors": store.live_visitors(), "disclaimer": store.DISCLAIMER})


@bp.get("/admin/api/visitors")
def admin_visitors():
    start = _day_start(request.args.get("from", ""))
    end = _day_end(request.args.get("to", ""))
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1
    return jsonify(
        store.list_visitors(
            q=(request.args.get("q") or "").strip()[:80],
            country=(request.args.get("country") or "").strip()[:80],
            city=(request.args.get("city") or "").strip()[:80],
            device=(request.args.get("device") or "").strip()[:40],
            gps=(request.args.get("gps") or "").strip(),
            start=start,
            end=end,
            sort=(request.args.get("sort") or "last_seen").strip(),
            direction=(request.args.get("dir") or "desc").strip().lower(),
            page=page,
            page_size=20,
        )
    )


@bp.get("/admin/api/visitors/<visitor_key>")
def admin_visitor(visitor_key: str):
    if not VISITOR_RE.fullmatch(visitor_key):
        abort(404)
    detail = store.visitor_detail(visitor_key)
    if detail is None:
        abort(404)
    return jsonify(detail)


@bp.post("/admin/api/visitors/<visitor_key>/delete")
def admin_delete_visitor(visitor_key: str):
    denied = _admin_write()
    if denied:
        return denied
    if not VISITOR_RE.fullmatch(visitor_key):
        abort(404)
    if not store.delete_visitor(visitor_key):
        abort(404)
    store.audit("delete_visitor", visitor_key, client_ip())
    return jsonify({"ok": True})


@bp.post("/admin/api/visitors/<visitor_key>/delete-gps")
def admin_delete_gps(visitor_key: str):
    denied = _admin_write()
    if denied:
        return denied
    if not VISITOR_RE.fullmatch(visitor_key):
        abort(404)
    removed = store.delete_gps(visitor_key)
    store.audit("delete_gps", visitor_key, client_ip())
    return jsonify({"ok": True, "removed": removed})


@bp.post("/admin/api/sessions/<session_key>/revoke")
def admin_revoke(session_key: str):
    denied = _admin_write()
    if denied:
        return denied
    if not SESSION_RE.fullmatch(session_key):
        abort(404)
    if not store.revoke_session(session_key):
        abort(404)
    store.audit("revoke_session", session_key, client_ip())
    return jsonify({"ok": True})


@bp.get("/admin/api/permissions")
def admin_permissions():
    return jsonify(store.permission_report())


@bp.get("/admin/api/devices")
def admin_devices():
    return jsonify(store.device_report())


@bp.get("/admin/api/sources")
def admin_sources():
    return jsonify({"sources": store.source_report()})


@bp.get("/admin/api/settings")
def admin_settings():
    return jsonify(store.settings_payload())


@bp.post("/admin/api/settings")
def admin_settings_save():
    denied = _admin_write()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    try:
        gps_days = int(payload.get("gps_retention_days"))
        activity_days = int(payload.get("activity_retention_days"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Enter retention in whole days."}), 400
    store.update_settings(gps_days, activity_days)
    store.audit("update_settings", None, client_ip())
    return jsonify({"ok": True, **store.settings_payload()})


@bp.post("/admin/api/export")
def admin_export():
    denied = _admin_write()
    if denied:
        return denied
    store.audit("export_csv", None, client_ip())
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "visitor_id",
            "ip_address",
            "ip_country",
            "ip_city",
            "device",
            "browser",
            "gps_status",
            "latitude",
            "longitude",
            "maps_url",
            "first_visit",
            "last_visit",
            "visit_count",
        ]
    )
    for row in store.export_rows():
        writer.writerow([_csv_safe(row.get(key)) for key in (
            "visitor_id",
            "ip_address",
            "ip_country",
            "ip_city",
            "device",
            "browser",
            "gps_status",
            "latitude",
            "longitude",
            "maps_url",
            "first_visit",
            "last_visit",
            "visit_count",
        )])
    return buffer.getvalue(), 200, {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": "attachment; filename=visitor-records.csv",
        "Cache-Control": "private, no-store",
    }


def _session_or_error():
    from flask import g

    row = getattr(g, "session_row", None)
    if not row:
        return jsonify({"ok": False, "error": "Reload this page and try again."}), 401
    return row


def _granted_analytics():
    from flask import g

    row = getattr(g, "session_row", None)
    if not row or not getattr(g, "access_granted", False):
        return jsonify({"ok": False}), 401
    if not csrf_ok():
        return jsonify({"ok": False}), 403
    return row


def _hit_limit(name: str, limit: int, window: int):
    ip = client_ip() or "unknown"
    if store.allow_rate(f"{name}:{ip}", limit, window):
        return None
    return jsonify({"ok": False, "error": "Too many attempts. Wait a few minutes and try again."}), 429


def _coord(value, low: float, high: float):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < low or number > high:
        return None
    return round(number, 6)


def _position_time(value) -> str | None:
    try:
        millis = int(value)
    except (TypeError, ValueError):
        return None
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if millis < 1_500_000_000_000 or millis > now_ms + 86_400_000:
        return None
    return datetime.fromtimestamp(millis / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _same_origin() -> bool:
    origin = request.headers.get("Origin")
    if not origin:
        return True
    return origin == request.host_url.rstrip("/")


def _admin_write():
    if request.headers.get("X-Requested-With") != "fetch" or not _same_origin():
        return jsonify({"ok": False, "error": "Blocked."}), 403
    return None


def _day_start(value: str) -> str:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value or ""):
        return value + "T00:00:00Z"
    return ""


def _day_end(value: str) -> str:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value or ""):
        return value + "T23:59:59Z"
    return ""


def _secret_match(sent: str, expected: str) -> bool:
    sent_bytes = sent.encode("utf-8")
    expected_bytes = expected.encode("utf-8")
    if len(sent_bytes) != len(expected_bytes):
        return False
    return hmac.compare_digest(sent_bytes, expected_bytes)


def _csv_safe(value) -> str:
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@"):
        return "'" + text
    return text

"""SQLite storage for visitor sessions, GPS fixes, and admin audit events."""

from __future__ import annotations

import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from visitor_intel.net import NOTICE_VERSION

LIVE_WINDOW_SECONDS = 120
SCHEMA = """
CREATE TABLE IF NOT EXISTS visitors (
  visitor_key TEXT PRIMARY KEY,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  visit_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
  session_key TEXT PRIMARY KEY,
  visitor_key TEXT NOT NULL REFERENCES visitors(visitor_key) ON DELETE CASCADE,
  started_at TEXT NOT NULL,
  last_activity_at TEXT NOT NULL,
  ended_at TEXT,
  expires_at TEXT NOT NULL,
  access_status TEXT NOT NULL,
  consent_status TEXT NOT NULL,
  landing_path TEXT,
  referrer TEXT,
  current_path TEXT,
  csrf_token TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS network (
  session_key TEXT PRIMARY KEY REFERENCES sessions(session_key) ON DELETE CASCADE,
  ip_address TEXT,
  ip_version TEXT,
  country TEXT,
  region TEXT,
  city TEXT,
  isp TEXT,
  asn TEXT,
  organization TEXT,
  latitude REAL,
  longitude REAL,
  provider TEXT,
  captured_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gps (
  session_key TEXT PRIMARY KEY REFERENCES sessions(session_key) ON DELETE CASCADE,
  latitude REAL,
  longitude REAL,
  accuracy_m REAL,
  position_at TEXT,
  captured_at TEXT NOT NULL,
  deleted_at TEXT,
  consent_id INTEGER
);
CREATE TABLE IF NOT EXISTS devices (
  session_key TEXT PRIMARY KEY REFERENCES sessions(session_key) ON DELETE CASCADE,
  device_type TEXT,
  device_model TEXT,
  browser TEXT,
  browser_version TEXT,
  os_name TEXT,
  os_version TEXT,
  screen_resolution TEXT,
  viewport TEXT,
  language TEXT,
  timezone TEXT,
  user_agent TEXT
);
CREATE TABLE IF NOT EXISTS activity (
  id INTEGER PRIMARY KEY,
  session_key TEXT NOT NULL REFERENCES sessions(session_key) ON DELETE CASCADE,
  page_path TEXT NOT NULL,
  referrer TEXT,
  event_type TEXT NOT NULL,
  occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS consents (
  id INTEGER PRIMARY KEY,
  session_key TEXT NOT NULL REFERENCES sessions(session_key) ON DELETE CASCADE,
  notice_version TEXT NOT NULL,
  consent_status TEXT NOT NULL,
  consented_at TEXT NOT NULL,
  withdrawn_at TEXT
);
CREATE TABLE IF NOT EXISTS permission_events (
  id INTEGER PRIMARY KEY,
  session_key TEXT REFERENCES sessions(session_key) ON DELETE CASCADE,
  event_name TEXT NOT NULL,
  occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_audit (
  id INTEGER PRIMARY KEY,
  action TEXT NOT NULL,
  target_key TEXT,
  ip_address TEXT,
  occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rate_buckets (
  bucket TEXT PRIMARY KEY,
  window_start TEXT NOT NULL,
  hits INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_visitor ON sessions(visitor_key, started_at);
CREATE INDEX IF NOT EXISTS idx_sessions_live ON sessions(last_activity_at);
CREATE INDEX IF NOT EXISTS idx_activity_session ON activity(session_key, occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_name ON permission_events(event_name, occurred_at);
"""


def db_path() -> Path:
    raw = os.environ.get("VISITOR_DB_PATH", "").strip()
    if raw:
        return Path(raw)
    if os.environ.get("VERCEL") == "1":
        return Path("/tmp/visitors.db")
    return Path(__file__).resolve().parents[1] / "data" / "visitors.db"


def storage_status() -> dict:
    path = db_path()
    ephemeral = str(path).startswith("/tmp")
    return {
        "engine": "sqlite",
        "ephemeral": ephemeral,
        "detail": (
            "Visitor records are on temporary serverless storage and can disappear when the host recycles. "
            "Set VISITOR_DB_PATH to a persistent disk for durable analytics."
            if ephemeral
            else "Visitor records are stored in a local SQLite file that persists across restarts."
        ),
    }


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def plus_hours(hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def session_hours() -> int:
    try:
        hours = int(os.environ.get("VISITOR_SESSION_HOURS", "24"))
    except ValueError:
        hours = 24
    return min(max(hours, 1), 168)


def timezone_name() -> str:
    name = os.environ.get("VISITOR_TIMEZONE", "Asia/Kolkata").strip() or "Asia/Kolkata"
    try:
        ZoneInfo(name)
    except Exception:
        return "UTC"
    return name


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass
    conn.executescript(SCHEMA)
    _ensure_settings(conn)
    return conn


@contextmanager
def db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_settings(conn: sqlite3.Connection) -> None:
    defaults = {
        "gps_retention_days": os.environ.get("VISITOR_GPS_RETENTION_DAYS", "30"),
        "activity_retention_days": os.environ.get("VISITOR_ACTIVITY_RETENTION_DAYS", "90"),
        "notice_version": NOTICE_VERSION,
    }
    for key, value in defaults.items():
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING",
            (key, str(value)),
        )


def setting_int(key: str, default: int, low: int, high: int) -> int:
    with db() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    try:
        value = int(row["value"]) if row else default
    except (TypeError, ValueError):
        value = default
    return min(max(value, low), high)


def update_settings(gps_days: int, activity_days: int) -> None:
    gps_days = min(max(int(gps_days), 1), 3650)
    activity_days = min(max(int(activity_days), 1), 3650)
    with db() as conn:
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES ('gps_retention_days', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(gps_days),),
        )
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES ('activity_retention_days', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(activity_days),),
        )


def allow_rate(bucket: str, limit: int, window_seconds: int) -> bool:
    current = now_iso()
    with db() as conn:
        row = conn.execute("SELECT window_start, hits FROM rate_buckets WHERE bucket = ?", (bucket,)).fetchone()
        if row is None or (parse_iso(current) - parse_iso(row["window_start"])).total_seconds() >= window_seconds:
            conn.execute(
                "INSERT INTO rate_buckets (bucket, window_start, hits) VALUES (?, ?, 1) "
                "ON CONFLICT(bucket) DO UPDATE SET window_start = excluded.window_start, hits = 1",
                (bucket, current),
            )
            return True
        if row["hits"] >= limit:
            return False
        conn.execute("UPDATE rate_buckets SET hits = hits + 1 WHERE bucket = ?", (bucket,))
        return True


def purge_expired() -> None:
    gps_days = setting_int("gps_retention_days", 30, 1, 3650)
    activity_days = setting_int("activity_retention_days", 90, 1, 3650)
    now = datetime.now(timezone.utc)
    gps_cutoff = (now - timedelta(days=gps_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    activity_cutoff = (now - timedelta(days=activity_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    audit_cutoff = (now - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with db() as conn:
        conn.execute(
            """
            UPDATE gps
            SET latitude = NULL, longitude = NULL, accuracy_m = NULL, deleted_at = ?
            WHERE captured_at < ? AND deleted_at IS NULL AND latitude IS NOT NULL
            """,
            (now_iso(), gps_cutoff),
        )
        conn.execute(
            """
            UPDATE network
            SET latitude = NULL, longitude = NULL
            WHERE captured_at < ? AND latitude IS NOT NULL
            """,
            (gps_cutoff,),
        )
        old_sessions = [
            row["session_key"]
            for row in conn.execute("SELECT session_key FROM sessions WHERE started_at < ?", (activity_cutoff,))
        ]
        if old_sessions:
            conn.executemany("DELETE FROM sessions WHERE session_key = ?", [(key,) for key in old_sessions])
        conn.execute(
            """
            DELETE FROM visitors
            WHERE last_seen_at < ?
              AND visitor_key NOT IN (SELECT visitor_key FROM sessions)
            """,
            (activity_cutoff,),
        )
        conn.execute("DELETE FROM admin_audit WHERE occurred_at < ?", (audit_cutoff,))
        conn.execute("DELETE FROM rate_buckets WHERE window_start < ?", (activity_cutoff,))


def new_visitor_key() -> str:
    return "v_" + secrets.token_hex(8)


def new_session_key() -> str:
    return "s_" + secrets.token_hex(16)


def get_session(session_key: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE session_key = ?", (session_key,)).fetchone()
    return dict(row) if row else None


def create_session(*, visitor_key: str | None, landing_path: str, referrer: str | None, network: dict, device: dict) -> dict:
    current = now_iso()
    visitor_key = visitor_key or new_visitor_key()
    session_key = new_session_key()
    csrf_token = secrets.token_urlsafe(32)
    expires_at = plus_hours(session_hours())
    with db() as conn:
        existing = conn.execute("SELECT visitor_key, visit_count FROM visitors WHERE visitor_key = ?", (visitor_key,)).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO visitors (visitor_key, first_seen_at, last_seen_at, visit_count) VALUES (?, ?, ?, 1)",
                (visitor_key, current, current),
            )
        else:
            conn.execute(
                "UPDATE visitors SET last_seen_at = ?, visit_count = visit_count + 1 WHERE visitor_key = ?",
                (current, visitor_key),
            )
        conn.execute(
            """
            INSERT INTO sessions (
              session_key, visitor_key, started_at, last_activity_at, expires_at,
              access_status, consent_status, landing_path, referrer, current_path, csrf_token
            ) VALUES (?, ?, ?, ?, ?, 'pending', 'unknown', ?, ?, ?, ?)
            """,
            (session_key, visitor_key, current, current, expires_at, landing_path, referrer, landing_path, csrf_token),
        )
        _insert_network(conn, session_key, network, current)
        _insert_device(conn, session_key, device)
    return get_session(session_key)


def _insert_network(conn, session_key: str, network: dict, captured_at: str) -> None:
    conn.execute(
        """
        INSERT INTO network (
          session_key, ip_address, ip_version, country, region, city, isp, asn,
          organization, latitude, longitude, provider, captured_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_key) DO UPDATE SET
          ip_address = excluded.ip_address,
          ip_version = excluded.ip_version,
          country = excluded.country,
          region = excluded.region,
          city = excluded.city,
          isp = excluded.isp,
          asn = excluded.asn,
          organization = excluded.organization,
          latitude = excluded.latitude,
          longitude = excluded.longitude,
          provider = excluded.provider,
          captured_at = excluded.captured_at
        """,
        (
            session_key,
            network.get("ip_address"),
            network.get("ip_version"),
            network.get("country"),
            network.get("region"),
            network.get("city"),
            network.get("isp"),
            network.get("asn"),
            network.get("organization"),
            network.get("latitude"),
            network.get("longitude"),
            network.get("provider"),
            captured_at,
        ),
    )


def _insert_device(conn, session_key: str, device: dict) -> None:
    conn.execute(
        """
        INSERT INTO devices (
          session_key, device_type, device_model, browser, browser_version, os_name,
          os_version, screen_resolution, viewport, language, timezone, user_agent
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_key) DO UPDATE SET
          device_type = COALESCE(excluded.device_type, devices.device_type),
          device_model = COALESCE(excluded.device_model, devices.device_model),
          browser = COALESCE(excluded.browser, devices.browser),
          browser_version = COALESCE(excluded.browser_version, devices.browser_version),
          os_name = COALESCE(excluded.os_name, devices.os_name),
          os_version = COALESCE(excluded.os_version, devices.os_version),
          screen_resolution = COALESCE(excluded.screen_resolution, devices.screen_resolution),
          viewport = COALESCE(excluded.viewport, devices.viewport),
          language = COALESCE(excluded.language, devices.language),
          timezone = COALESCE(excluded.timezone, devices.timezone),
          user_agent = COALESCE(excluded.user_agent, devices.user_agent)
        """,
        (
            session_key,
            device.get("device_type"),
            device.get("device_model"),
            device.get("browser"),
            device.get("browser_version"),
            device.get("os_name"),
            device.get("os_version"),
            device.get("screen_resolution"),
            device.get("viewport"),
            device.get("language"),
            device.get("timezone"),
            device.get("user_agent"),
        ),
    )


def session_is_granted(row: dict | None) -> bool:
    if not row:
        return False
    if row.get("access_status") != "granted":
        return False
    return row.get("expires_at", "") > now_iso()


def mark_ended(session_key: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE sessions SET ended_at = COALESCE(ended_at, ?) WHERE session_key = ?",
            (now_iso(), session_key),
        )


def add_permission_event(session_key: str, event_name: str) -> None:
    allowed = {"denied", "dismissed", "unavailable", "timeout", "unsupported", "collected", "server_rejected"}
    if event_name not in allowed:
        raise ValueError("unsupported event")
    with db() as conn:
        conn.execute(
            "INSERT INTO permission_events (session_key, event_name, occurred_at) VALUES (?, ?, ?)",
            (session_key, event_name, now_iso()),
        )


def record_outcome(session_key: str, status: str) -> None:
    allowed = {"denied", "dismissed", "unavailable", "timeout", "unsupported"}
    if status not in allowed:
        raise ValueError("unsupported outcome")
    current = now_iso()
    with db() as conn:
        recent = conn.execute(
            """
            SELECT id FROM permission_events
            WHERE session_key = ? AND event_name = ? AND occurred_at > ?
            """,
            (session_key, status, _seconds_ago(30)),
        ).fetchone()
        if recent is None:
            conn.execute(
                "INSERT INTO permission_events (session_key, event_name, occurred_at) VALUES (?, ?, ?)",
                (session_key, status, current),
            )
        conn.execute(
            "INSERT INTO consents (session_key, notice_version, consent_status, consented_at) VALUES (?, ?, ?, ?)",
            (session_key, NOTICE_VERSION, status, current),
        )
        conn.execute(
            """
            UPDATE sessions
            SET consent_status = ?, last_activity_at = ?
            WHERE session_key = ? AND access_status != 'granted'
            """,
            (status, current, session_key),
        )


def store_gps(session_key: str, *, latitude: float, longitude: float, accuracy_m: float, position_at: str | None, device_extra: dict) -> tuple[bool, bool]:
    """Save a GPS fix. Returns (saved, first_grant)."""
    current = now_iso()
    with db() as conn:
        row = conn.execute("SELECT access_status FROM sessions WHERE session_key = ?", (session_key,)).fetchone()
        if row is None:
            return False, False
        if row["access_status"] == "revoked":
            return False, False
        existing = conn.execute("SELECT latitude, deleted_at FROM gps WHERE session_key = ?", (session_key,)).fetchone()
        if existing and existing["latitude"] is not None:
            conn.execute(
                "UPDATE sessions SET access_status = 'granted', consent_status = 'granted', last_activity_at = ? WHERE session_key = ? AND access_status != 'revoked'",
                (current, session_key),
            )
            return True, False
        consent = conn.execute(
            "INSERT INTO consents (session_key, notice_version, consent_status, consented_at) VALUES (?, ?, 'granted', ?)",
            (session_key, NOTICE_VERSION, current),
        )
        conn.execute(
            """
            INSERT INTO gps (session_key, latitude, longitude, accuracy_m, position_at, captured_at, consent_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_key) DO UPDATE SET
              latitude = excluded.latitude,
              longitude = excluded.longitude,
              accuracy_m = excluded.accuracy_m,
              position_at = excluded.position_at,
              captured_at = excluded.captured_at,
              deleted_at = NULL,
              consent_id = excluded.consent_id
            """,
            (session_key, latitude, longitude, accuracy_m, position_at, current, consent.lastrowid),
        )
        conn.execute(
            """
            UPDATE sessions
            SET access_status = 'granted', consent_status = 'granted', expires_at = ?, last_activity_at = ?
            WHERE session_key = ? AND access_status != 'revoked'
            """,
            (plus_hours(session_hours()), current, session_key),
        )
        conn.execute(
            "INSERT INTO permission_events (session_key, event_name, occurred_at) VALUES (?, 'collected', ?)",
            (session_key, current),
        )
        if device_extra:
            _insert_device(conn, session_key, device_extra)
        return True, True


def touch(session_key: str, path: str, *, event_type: str, referrer: str | None = None) -> None:
    current = now_iso()
    with db() as conn:
        conn.execute(
            "UPDATE sessions SET last_activity_at = ?, current_path = ? WHERE session_key = ?",
            (current, path, session_key),
        )
        if event_type != "pageview":
            return
        recent = conn.execute(
            """
            SELECT id FROM activity
            WHERE session_key = ? AND event_type = 'pageview' AND page_path = ? AND occurred_at > ?
            """,
            (session_key, path, _seconds_ago(10)),
        ).fetchone()
        if recent:
            return
        conn.execute(
            "INSERT INTO activity (session_key, page_path, referrer, event_type, occurred_at) VALUES (?, ?, ?, 'pageview', ?)",
            (session_key, path, referrer, current),
        )


def _seconds_ago(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def audit(action: str, target: str | None, ip_address: str | None) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO admin_audit (action, target_key, ip_address, occurred_at) VALUES (?, ?, ?, ?)",
            (action, target, ip_address, now_iso()),
        )


def overview() -> dict:
    purge_expired()
    tz = ZoneInfo(timezone_name())
    local_now = datetime.now(tz)
    start_today = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    start_7 = (local_now - timedelta(days=7)).astimezone(timezone.utc)
    start_30 = (local_now - timedelta(days=30)).astimezone(timezone.utc)
    with db() as conn:
        visitors = conn.execute("SELECT visitor_key, first_seen_at, visit_count FROM visitors").fetchall()
        sessions = conn.execute(
            "SELECT session_key, visitor_key, started_at, last_activity_at, access_status, consent_status, current_path FROM sessions"
        ).fetchall()
        gps_count = conn.execute("SELECT COUNT(*) AS n FROM gps WHERE latitude IS NOT NULL").fetchone()["n"]
        denied = conn.execute("SELECT COUNT(*) AS n FROM sessions WHERE consent_status = 'denied'").fetchone()["n"]
        pages = conn.execute(
            """
            SELECT page_path, COUNT(*) AS n FROM activity
            WHERE event_type = 'pageview' GROUP BY page_path ORDER BY n DESC LIMIT 8
            """
        ).fetchall()
        countries = conn.execute(
            """
            SELECT COALESCE(country, 'Unavailable') AS name, COUNT(*) AS n
            FROM network GROUP BY name ORDER BY n DESC LIMIT 8
            """
        ).fetchall()
        cities = conn.execute(
            """
            SELECT COALESCE(city, 'Unavailable') AS name, COUNT(*) AS n
            FROM network GROUP BY name ORDER BY n DESC LIMIT 8
            """
        ).fetchall()
        devices = conn.execute(
            """
            SELECT COALESCE(device_type, 'Unavailable') AS name, COUNT(*) AS n
            FROM devices GROUP BY name ORDER BY n DESC
            """
        ).fetchall()
        events = conn.execute(
            "SELECT event_name, COUNT(*) AS n FROM permission_events GROUP BY event_name"
        ).fetchall()
    today_key = start_today.strftime("%Y-%m-%dT%H:%M:%SZ")
    key_7 = start_7.strftime("%Y-%m-%dT%H:%M:%SZ")
    key_30 = start_30.strftime("%Y-%m-%dT%H:%M:%SZ")
    live_after = _seconds_ago(LIVE_WINDOW_SECONDS)

    def distinct_since(cutoff: str) -> int:
        return len({row["visitor_key"] for row in sessions if row["started_at"] >= cutoff})

    durations = []
    for row in sessions:
        if row["access_status"] != "granted":
            continue
        started = parse_iso(row["started_at"])
        last = parse_iso(row["last_activity_at"])
        durations.append(max((last - started).total_seconds(), 0))
    series = []
    for offset in range(13, -1, -1):
        day = (local_now - timedelta(days=offset)).date()
        day_start = datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(timezone.utc)
        day_end = day_start + timedelta(days=1)
        start_s = day_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_s = day_end.strftime("%Y-%m-%dT%H:%M:%SZ")
        day_rows = [row for row in sessions if start_s <= row["started_at"] < end_s]
        series.append(
            {
                "day": day.isoformat(),
                "visits": len(day_rows),
                "uniques": len({row["visitor_key"] for row in day_rows}),
            }
        )
    event_map = {row["event_name"]: row["n"] for row in events}
    active = sum(
        1
        for row in sessions
        if row["access_status"] == "granted" and row["last_activity_at"] >= live_after
    )
    return {
        "timezone": timezone_name(),
        "live_window_seconds": LIVE_WINDOW_SECONDS,
        "storage": storage_status(),
        "notice_version": NOTICE_VERSION,
        "totals": {
            "visits": len(sessions),
            "unique_visitors": len(visitors),
            "today": distinct_since(today_key),
            "last_7_days": distinct_since(key_7),
            "last_30_days": distinct_since(key_30),
            "returning": sum(1 for row in visitors if row["visit_count"] >= 2),
            "new_today": sum(1 for row in visitors if row["first_seen_at"] >= today_key),
            "gps_stored": gps_count,
            "gps_denied": denied,
            "active_sessions": active,
            "avg_duration_seconds": round(sum(durations) / len(durations)) if durations else None,
        },
        "series": series,
        "pages": [{"path": row["page_path"], "views": row["n"]} for row in pages],
        "countries": [{"name": row["name"], "count": row["n"]} for row in countries],
        "cities": [{"name": row["name"], "count": row["n"]} for row in cities],
        "devices": [{"name": row["name"], "count": row["n"]} for row in devices],
        "permissions": event_map,
        "disclaimer": DISCLAIMER,
    }


def visit_summary(session_key: str) -> dict | None:
    with db() as conn:
        row = conn.execute(
            """
            SELECT s.visitor_key, s.session_key, s.started_at, s.access_status, s.consent_status,
                   s.landing_path, s.referrer,
                   v.visit_count,
                   n.ip_address, n.ip_version, n.city, n.region, n.country, n.isp, n.asn,
                   n.organization, n.latitude AS ip_latitude, n.longitude AS ip_longitude, n.provider,
                   g.latitude, g.longitude, g.accuracy_m, g.captured_at, g.position_at,
                   d.device_type, d.device_model, d.browser, d.browser_version, d.os_name, d.os_version,
                   d.language, d.timezone AS device_timezone, d.screen_resolution, d.viewport
            FROM sessions s
            LEFT JOIN visitors v ON v.visitor_key = s.visitor_key
            LEFT JOIN network n ON n.session_key = s.session_key
            LEFT JOIN gps g ON g.session_key = s.session_key
            LEFT JOIN devices d ON d.session_key = s.session_key
            WHERE s.session_key = ?
            """,
            (session_key,),
        ).fetchone()
    if row is None:
        return None
    latitude = row["latitude"]
    longitude = row["longitude"]
    return {
        "visitor_key": row["visitor_key"],
        "session_key": row["session_key"],
        "visit_count": row["visit_count"],
        "started_at": row["started_at"],
        "access_status": row["access_status"],
        "consent_status": row["consent_status"],
        "landing_path": row["landing_path"] or "/",
        "referrer": row["referrer"],
        "ip_address": row["ip_address"],
        "ip_version": row["ip_version"],
        "city": row["city"],
        "region": row["region"],
        "country": row["country"],
        "isp": row["isp"],
        "asn": row["asn"],
        "organization": row["organization"],
        "ip_latitude": row["ip_latitude"],
        "ip_longitude": row["ip_longitude"],
        "ip_maps_url": google_maps_url(row["ip_latitude"], row["ip_longitude"]),
        "ip_provider": row["provider"],
        "latitude": latitude,
        "longitude": longitude,
        "accuracy_m": row["accuracy_m"],
        "captured_at": row["captured_at"],
        "position_at": row["position_at"],
        "device_type": row["device_type"],
        "device_model": row["device_model"],
        "browser": row["browser"],
        "browser_version": row["browser_version"],
        "os_name": row["os_name"],
        "os_version": row["os_version"],
        "language": row["language"],
        "device_timezone": row["device_timezone"],
        "screen_resolution": row["screen_resolution"],
        "viewport": row["viewport"],
        "maps_url": google_maps_url(latitude, longitude),
        "timezone": timezone_name(),
    }


def google_maps_url(latitude, longitude) -> str | None:
    if latitude is None or longitude is None:
        return None
    return f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"


DISCLAIMER = (
    "IP coordinates are an estimate from a geolocation provider, not GPS and not a street address. "
    "GPS coordinates are a one-time browser reading with the reported accuracy. "
    "Neither source proves who a visitor is. Separate sessions from the same network are not assumed to be the same person."
)


def live_visitors() -> list[dict]:
    cutoff = _seconds_ago(LIVE_WINDOW_SECONDS)
    with db() as conn:
        rows = conn.execute(
            """
            SELECT s.session_key, s.visitor_key, s.started_at, s.last_activity_at, s.current_path,
                   n.ip_address, n.city, n.country,
                   g.latitude AS gps_lat, g.longitude AS gps_lng,
                   d.device_type, d.browser, d.os_name
            FROM sessions s
            LEFT JOIN network n ON n.session_key = s.session_key
            LEFT JOIN gps g ON g.session_key = s.session_key
            LEFT JOIN devices d ON d.session_key = s.session_key
            WHERE s.access_status = 'granted' AND s.last_activity_at >= ?
            ORDER BY s.last_activity_at DESC
            """,
            (cutoff,),
        ).fetchall()
    results = []
    for row in rows:
        started = parse_iso(row["started_at"])
        last = parse_iso(row["last_activity_at"])
        results.append(
            {
                "visitor_id": row["visitor_key"],
                "session_id": row["session_key"],
                "current_page": row["current_path"] or "/",
                "ip_address": row["ip_address"] or "Unavailable",
                "ip_city": row["city"] or "Unavailable",
                "ip_country": row["country"] or "Unavailable",
                "gps_status": "GPS verified" if row["gps_lat"] is not None else "No GPS fix",
                "latitude": row["gps_lat"],
                "longitude": row["gps_lng"],
                "maps_url": google_maps_url(row["gps_lat"], row["gps_lng"]),
                "device": row["device_type"] or "Unavailable",
                "browser": row["browser"] or "Unavailable",
                "os": row["os_name"] or "Unavailable",
                "first_seen": row["started_at"],
                "last_active": row["last_activity_at"],
                "duration_seconds": max(int((last - started).total_seconds()), 0),
            }
        )
    return results


def list_visitors(*, q: str, country: str, city: str, device: str, gps: str, start: str, end: str, sort: str, direction: str, page: int, page_size: int) -> dict:
    sort_map = {
        "last_seen": "v.last_seen_at",
        "first_seen": "v.first_seen_at",
        "visits": "v.visit_count",
        "country": "ip_country",
        "city": "ip_city",
    }
    sort_sql = sort_map.get(sort, "v.last_seen_at")
    direction_sql = "ASC" if direction == "asc" else "DESC"
    where = ["1 = 1"]
    args: list = []
    if q:
        where.append(
            "(v.visitor_key LIKE ? ESCAPE '\\' OR IFNULL(n.ip_address,'') LIKE ? ESCAPE '\\' "
            "OR IFNULL(n.city,'') LIKE ? ESCAPE '\\' OR IFNULL(n.country,'') LIKE ? ESCAPE '\\')"
        )
        like = _like(q)
        args.extend([like, like, like, like])
    if country:
        where.append("n.country = ?")
        args.append(country)
    if city:
        where.append("n.city LIKE ? ESCAPE '\\'")
        args.append(_like(city))
    if device:
        where.append("d.device_type = ?")
        args.append(device)
    if gps == "granted":
        where.append("g.latitude IS NOT NULL")
    elif gps == "denied":
        where.append("s.consent_status = 'denied'")
    elif gps == "none":
        where.append("g.latitude IS NULL AND s.consent_status NOT IN ('denied', 'dismissed')")
    if start:
        where.append("v.last_seen_at >= ?")
        args.append(start)
    if end:
        where.append("v.last_seen_at <= ?")
        args.append(end)
    where_sql = " AND ".join(where)
    base = f"""
        FROM visitors v
        JOIN sessions s ON s.session_key = (
          SELECT session_key FROM sessions WHERE visitor_key = v.visitor_key ORDER BY started_at DESC LIMIT 1
        )
        LEFT JOIN network n ON n.session_key = s.session_key
        LEFT JOIN devices d ON d.session_key = s.session_key
        LEFT JOIN gps g ON g.session_key = s.session_key
        WHERE {where_sql}
    """
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    offset = (page - 1) * page_size
    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS n {base}", args).fetchone()["n"]
        rows = conn.execute(
            f"""
            SELECT v.visitor_key, v.first_seen_at, v.last_seen_at, v.visit_count,
                   n.ip_address, n.country AS ip_country, n.city AS ip_city,
                   g.latitude AS gps_latitude, g.longitude AS gps_longitude,
                   d.device_type, d.browser, s.consent_status,
                   CASE WHEN g.latitude IS NOT NULL THEN 'granted' ELSE s.consent_status END AS gps_status
            {base}
            ORDER BY {sort_sql} {direction_sql}
            LIMIT ? OFFSET ?
            """,
            [*args, page_size, offset],
        ).fetchall()
        countries = [row["country"] for row in conn.execute("SELECT DISTINCT country FROM network WHERE country IS NOT NULL ORDER BY country")]
        devices = [row["device_type"] for row in conn.execute("SELECT DISTINCT device_type FROM devices WHERE device_type IS NOT NULL ORDER BY device_type")]
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "facets": {"countries": countries, "devices": devices},
        "rows": [
            {
                "visitor_id": row["visitor_key"],
                "ip_address": row["ip_address"] or "Unavailable",
                "ip_country": row["ip_country"] or "Unavailable",
                "ip_city": row["ip_city"] or "Unavailable",
                "device": row["device_type"] or "Unavailable",
                "browser": row["browser"] or "Unavailable",
                "gps_status": _gps_label(row["gps_status"]),
                "latitude": row["gps_latitude"],
                "longitude": row["gps_longitude"],
                "maps_url": google_maps_url(row["gps_latitude"], row["gps_longitude"]),
                "first_visit": row["first_seen_at"],
                "last_visit": row["last_seen_at"],
                "visit_count": row["visit_count"],
            }
            for row in rows
        ],
    }


def _gps_label(status: str | None) -> str:
    if status == "granted":
        return "GPS verified"
    if status == "denied":
        return "Permission denied"
    if status == "dismissed":
        return "Permission dismissed"
    if status in {"unavailable", "timeout", "unsupported"}:
        return status.replace("_", " ").capitalize()
    return "No GPS fix"


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def visitor_detail(visitor_key: str) -> dict | None:
    with db() as conn:
        visitor = conn.execute("SELECT * FROM visitors WHERE visitor_key = ?", (visitor_key,)).fetchone()
        if visitor is None:
            return None
        sessions = conn.execute(
            "SELECT * FROM sessions WHERE visitor_key = ? ORDER BY started_at DESC",
            (visitor_key,),
        ).fetchall()
        payload_sessions = []
        for session in sessions:
            key = session["session_key"]
            network = conn.execute("SELECT * FROM network WHERE session_key = ?", (key,)).fetchone()
            gps = conn.execute("SELECT * FROM gps WHERE session_key = ?", (key,)).fetchone()
            device = conn.execute("SELECT * FROM devices WHERE session_key = ?", (key,)).fetchone()
            activity = conn.execute(
                "SELECT page_path, referrer, occurred_at FROM activity WHERE session_key = ? AND event_type = 'pageview' ORDER BY occurred_at",
                (key,),
            ).fetchall()
            consents = conn.execute(
                "SELECT notice_version, consent_status, consented_at, withdrawn_at FROM consents WHERE session_key = ? ORDER BY id",
                (key,),
            ).fetchall()
            pages = [row["page_path"] for row in activity]
            started = parse_iso(session["started_at"])
            last = parse_iso(session["last_activity_at"])
            payload_sessions.append(
                {
                    "session_id": key,
                    "started_at": session["started_at"],
                    "last_activity_at": session["last_activity_at"],
                    "ended_at": session["ended_at"],
                    "expires_at": session["expires_at"],
                    "access_status": session["access_status"],
                    "consent_status": session["consent_status"],
                    "entry_page": pages[0] if pages else session["landing_path"],
                    "exit_page": pages[-1] if pages else session["current_path"],
                    "duration_seconds": max(int((last - started).total_seconds()), 0),
                    "pages": [dict(row) for row in activity],
                    "ip": _public_network(network),
                    "gps": _public_gps(gps),
                    "device": dict(device) if device else None,
                    "consents": [dict(row) for row in consents],
                    "referrer": session["referrer"] or "Direct",
                }
            )
    return {
        "visitor_id": visitor["visitor_key"],
        "first_seen_at": visitor["first_seen_at"],
        "last_seen_at": visitor["last_seen_at"],
        "visit_count": visitor["visit_count"],
        "sessions": payload_sessions,
        "disclaimer": DISCLAIMER,
    }


def _public_network(row) -> dict | None:
    if row is None:
        return None
    return {
        "ip_address": row["ip_address"] or "Unavailable",
        "ip_version": row["ip_version"],
        "country": row["country"],
        "region": row["region"],
        "city": row["city"],
        "isp": row["isp"],
        "asn": row["asn"],
        "organization": row["organization"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "maps_url": google_maps_url(row["latitude"], row["longitude"]),
        "provider": row["provider"],
        "source_label": "IP estimated location",
        "captured_at": row["captured_at"],
    }


def _public_gps(row) -> dict | None:
    if row is None:
        return None
    deleted = row["deleted_at"] is not None or row["latitude"] is None
    return {
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "maps_url": google_maps_url(row["latitude"], row["longitude"]),
        "accuracy_m": row["accuracy_m"],
        "position_at": row["position_at"],
        "captured_at": row["captured_at"],
        "deleted_at": row["deleted_at"],
        "source_label": "GPS coordinates deleted" if deleted else "GPS verified location",
    }


def delete_visitor(visitor_key: str) -> bool:
    with db() as conn:
        cursor = conn.execute("DELETE FROM visitors WHERE visitor_key = ?", (visitor_key,))
        return cursor.rowcount > 0


def delete_gps(visitor_key: str) -> int:
    current = now_iso()
    with db() as conn:
        cursor = conn.execute(
            """
            UPDATE gps
            SET latitude = NULL, longitude = NULL, accuracy_m = NULL, deleted_at = ?
            WHERE session_key IN (SELECT session_key FROM sessions WHERE visitor_key = ?)
              AND latitude IS NOT NULL
            """,
            (current, visitor_key),
        )
        conn.execute(
            """
            UPDATE consents
            SET withdrawn_at = ?
            WHERE session_key IN (SELECT session_key FROM sessions WHERE visitor_key = ?)
              AND consent_status = 'granted' AND withdrawn_at IS NULL
            """,
            (current, visitor_key),
        )
        return cursor.rowcount


def revoke_session(session_key: str) -> bool:
    with db() as conn:
        cursor = conn.execute(
            "UPDATE sessions SET access_status = 'revoked', ended_at = ? WHERE session_key = ? AND access_status != 'revoked'",
            (now_iso(), session_key),
        )
        return cursor.rowcount > 0


def permission_report() -> dict:
    with db() as conn:
        rows = conn.execute(
            "SELECT event_name, occurred_at FROM permission_events ORDER BY occurred_at"
        ).fetchall()
    counts = {
        "collected": 0,
        "denied": 0,
        "dismissed": 0,
        "unavailable": 0,
        "timeout": 0,
        "unsupported": 0,
        "server_rejected": 0,
    }
    for row in rows:
        if row["event_name"] in counts:
            counts[row["event_name"]] += 1
    attempts = sum(counts.values())
    percents = {
        key: round((value / attempts) * 100, 1) if attempts else 0
        for key, value in counts.items()
    }
    tz = ZoneInfo(timezone_name())
    local_now = datetime.now(tz)
    series = []
    for offset in range(13, -1, -1):
        day = (local_now - timedelta(days=offset)).date()
        day_start = datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(timezone.utc)
        day_end = day_start + timedelta(days=1)
        start_s = day_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_s = day_end.strftime("%Y-%m-%dT%H:%M:%SZ")
        day_rows = [row for row in rows if start_s <= row["occurred_at"] < end_s]
        series.append(
            {
                "day": day.isoformat(),
                "collected": sum(1 for row in day_rows if row["event_name"] == "collected"),
                "denied": sum(1 for row in day_rows if row["event_name"] == "denied"),
                "other_failures": sum(1 for row in day_rows if row["event_name"] not in {"collected", "denied"}),
            }
        )
    return {
        "counts": counts,
        "percents": percents,
        "attempts": attempts,
        "series": series,
        "note": (
            "Collected means the browser returned coordinates and the server stored them. "
            "Denied and dismissed are browser permission outcomes, not successful collections."
        ),
    }


def device_report() -> dict:
    with db() as conn:
        browsers = conn.execute(
            """
            SELECT COALESCE(browser, 'Unavailable') AS name,
                   COALESCE(browser_version, '') AS version,
                   COUNT(*) AS n
            FROM devices GROUP BY name, version ORDER BY n DESC LIMIT 12
            """
        ).fetchall()
        systems = conn.execute(
            """
            SELECT COALESCE(os_name, 'Unavailable') AS name, COUNT(*) AS n
            FROM devices GROUP BY name ORDER BY n DESC
            """
        ).fetchall()
        types = conn.execute(
            """
            SELECT COALESCE(device_type, 'Unavailable') AS name, COUNT(*) AS n
            FROM devices GROUP BY name ORDER BY n DESC
            """
        ).fetchall()
    return {
        "browsers": [{"name": row["name"], "version": row["version"] or "Unavailable", "count": row["n"]} for row in browsers],
        "systems": [{"name": row["name"], "count": row["n"]} for row in systems],
        "devices": [{"name": row["name"], "count": row["n"]} for row in types],
    }


def source_report() -> list[dict]:
    from urllib.parse import urlparse

    with db() as conn:
        rows = conn.execute("SELECT referrer FROM sessions").fetchall()
    counts: dict[str, int] = {}
    for row in rows:
        ref = row["referrer"] or ""
        if not ref:
            label = "Direct"
        else:
            parsed = urlparse(ref)
            label = parsed.netloc or "Unavailable"
        counts[label] = counts.get(label, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    return [{"source": name, "count": count} for name, count in ordered[:20]]


def settings_payload() -> dict:
    return {
        "gps_retention_days": setting_int("gps_retention_days", 30, 1, 3650),
        "activity_retention_days": setting_int("activity_retention_days", 90, 1, 3650),
        "session_hours": session_hours(),
        "notice_version": NOTICE_VERSION,
        "storage": storage_status(),
        "timezone": timezone_name(),
    }


def export_rows() -> list[dict]:
    listed = list_visitors(q="", country="", city="", device="", gps="", start="", end="", sort="last_seen", direction="desc", page=1, page_size=100)
    rows = list(listed["rows"])
    page = 2
    while len(rows) < listed["total"] and page < 50:
        more = list_visitors(q="", country="", city="", device="", gps="", start="", end="", sort="last_seen", direction="desc", page=page, page_size=100)
        rows.extend(more["rows"])
        page += 1
    return rows

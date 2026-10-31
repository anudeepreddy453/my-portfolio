"""Server-issued visitor sessions. A browser flag alone never unlocks the site."""

from __future__ import annotations

import hmac
import os

from flask import g, make_response, render_template, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from visitor_intel import store
from visitor_intel.net import NOTICE_VERSION, clean_path, extract_ip, lookup_ip, parse_user_agent

VISITOR_COOKIE = "pv_v"
SESSION_COOKIE = "pv_s"
VISITOR_MAX_AGE = 180 * 24 * 3600


def client_ip() -> str:
    return extract_ip(
        request.remote_addr,
        request.headers,
        on_vercel=os.environ.get("VERCEL") == "1",
        trust_proxy=os.environ.get("TRUST_PROXY") == "1",
    )


def cookie_secure() -> bool:
    if os.environ.get("VERCEL") == "1":
        return True
    return bool(request.is_secure)


def _serializer() -> URLSafeTimedSerializer:
    secret = os.environ.get("FLASK_SECRET_KEY") or "local-dev-only-change-me"
    return URLSafeTimedSerializer(secret, salt="pv-visitor-v1")


def _read_cookie(name: str, max_age: int) -> str | None:
    raw = request.cookies.get(name, "")
    if not raw:
        return None
    try:
        data = _serializer().loads(raw, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    key = data.get("k")
    return key if isinstance(key, str) else None


def _queue_cookie(name: str, key: str, max_age: int) -> None:
    token = _serializer().dumps({"k": key})
    g.cookie_jar.append((name, token, max_age))


def apply_cookies(response):
    for name, value, max_age in getattr(g, "cookie_jar", []):
        response.set_cookie(
            name,
            value,
            max_age=max_age,
            httponly=True,
            secure=cookie_secure(),
            samesite="Lax",
            path="/",
        )
    return response


def attach(*, create: bool) -> None:
    """Load the visitor session for this request. Optionally open a pending one."""
    if getattr(g, "visitor_attached", False):
        return
    g.visitor_attached = True
    g.cookie_jar = []
    g.access_granted = False
    g.csrf_token = ""
    g.session_row = None
    g.visitor_key = None
    g.rate_limited = False

    visitor_key = _read_cookie(VISITOR_COOKIE, VISITOR_MAX_AGE)
    session_key = _read_cookie(SESSION_COOKIE, store.session_hours() * 3600)
    row = store.get_session(session_key) if session_key else None
    current = store.now_iso()
    if row and row["access_status"] == "revoked":
        row = None
    elif row and row["expires_at"] <= current:
        store.mark_ended(row["session_key"])
        row = None
    elif row and visitor_key and row["visitor_key"] != visitor_key:
        row = None

    if row:
        g.session_row = row
        g.visitor_key = row["visitor_key"]
        g.csrf_token = row["csrf_token"]
        g.access_granted = store.session_is_granted(row)
        if not visitor_key:
            _queue_cookie(VISITOR_COOKIE, row["visitor_key"], VISITOR_MAX_AGE)
        return

    if not create:
        return

    ip = client_ip()
    if not store.allow_rate(f"session:{ip or 'unknown'}", 30, 3600):
        g.rate_limited = True
        return

    device = parse_user_agent(request.headers.get("User-Agent"))
    if request.accept_languages:
        device["language"] = request.accept_languages.best
    created = store.create_session(
        visitor_key=visitor_key,
        landing_path=clean_path(request.path),
        referrer=(request.referrer or "")[:500] or None,
        network=lookup_ip(ip),
        device=device,
    )
    g.session_row = created
    g.visitor_key = created["visitor_key"]
    g.csrf_token = created["csrf_token"]
    _queue_cookie(VISITOR_COOKIE, created["visitor_key"], VISITOR_MAX_AGE)
    _queue_cookie(SESSION_COOKIE, created["session_key"], store.session_hours() * 3600)


def refresh_session_cookie() -> None:
    row = getattr(g, "session_row", None)
    if row:
        _queue_cookie(SESSION_COOKIE, row["session_key"], store.session_hours() * 3600)


def csrf_ok() -> bool:
    row = getattr(g, "session_row", None)
    sent = request.headers.get("X-CSRF-Token", "")
    expected = (row or {}).get("csrf_token") or ""
    if not sent or not expected:
        return False
    return hmac.compare_digest(sent, expected)


def render_gate(status: int = 200):
    response = make_response(
        render_template(
            "gate.html",
            csrf_token=getattr(g, "csrf_token", ""),
            rate_limited=bool(getattr(g, "rate_limited", False)),
            notice_version=NOTICE_VERSION,
        ),
        status,
    )
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Permissions-Policy"] = "geolocation=(self)"
    return response


def locked_response(status: int = 200):
    """Return the gate when this request has no granted server session."""
    if getattr(g, "access_granted", False):
        return None
    return render_gate(status)

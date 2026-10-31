"""One email when a visitor grants location and the portfolio unlocks."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

DEFAULT_EMAIL = "anudeepreddy453@gmail.com"
DEFAULT_FROM = "Portfolio <onboarding@resend.dev>"


def visit_granted(summary: dict | None) -> None:
    if not summary:
        return
    try:
        if not _api_key():
            return
        deliver(_message(summary))
    except Exception:
        log.warning("Visit email was not sent", exc_info=True)


def deliver(message: dict) -> None:
    key = _api_key()
    if not key:
        return
    body = json.dumps(message).encode("utf-8")
    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "portfolio-visitor-notice",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        log.warning("Resend returned %s: %s", error.code, detail)


def _message(summary: dict) -> dict:
    place = _place(summary)
    subject = "Portfolio visit"
    if place != "Unavailable":
        subject = f"Portfolio visit from {place}"
    return {
        "from": os.environ.get("VISITOR_NOTIFY_FROM", DEFAULT_FROM).strip() or DEFAULT_FROM,
        "to": [_recipient()],
        "subject": subject,
        "text": _body(summary, place),
    }


def _body(summary: dict, place: str) -> str:
    zone = summary.get("timezone") or "Asia/Kolkata"
    browser = _joined(summary.get("browser"), summary.get("browser_version"))
    system = _joined(summary.get("os_name"), summary.get("os_version"))
    accuracy = summary.get("accuracy_m")
    accuracy_line = "Unavailable" if accuracy is None else f"{round(float(accuracy))} m"
    lines = [
        "Someone allowed location and opened your portfolio.",
        "",
        "Visitor",
        _line("ID", summary.get("visitor_key")),
        _line("Visits", summary.get("visit_count")),
        _line("Session", summary.get("session_key")),
        _line("Access", summary.get("access_status")),
        _line("Consent", summary.get("consent_status")),
        _line("Started", _format_time(summary.get("started_at"), zone)),
        _line("Referrer", summary.get("referrer") or "Direct"),
        _line("Opened", summary.get("landing_path") or "/"),
        "",
        "GPS verified location",
        _line("Coordinates", _coordinates(summary.get("latitude"), summary.get("longitude"))),
        _line("Map", summary.get("maps_url")),
        _line("Accuracy", accuracy_line),
        _line("Captured", _format_time(summary.get("captured_at"), zone)),
        _line("Device time", _format_time(summary.get("position_at"), zone)),
        "",
        "IP estimated location",
        _line("Place", place),
        _line("IP", summary.get("ip_address")),
        _line("Version", summary.get("ip_version")),
        _line("City", summary.get("city")),
        _line("Region", summary.get("region")),
        _line("Country", summary.get("country")),
        _line("ISP", summary.get("isp")),
        _line("ASN", summary.get("asn")),
        _line("Organization", summary.get("organization")),
        _line("Estimated coordinates", _coordinates(summary.get("ip_latitude"), summary.get("ip_longitude"))),
        _line("Estimated map", summary.get("ip_maps_url")),
        _line("Provider", summary.get("ip_provider")),
        "",
        "Device",
        _line("Type", summary.get("device_type")),
        _line("Model", summary.get("device_model")),
        _line("Browser", browser),
        _line("System", system),
        _line("Language", summary.get("language")),
        _line("Time zone", summary.get("device_timezone")),
        _line("Screen", summary.get("screen_resolution")),
        _line("Viewport", summary.get("viewport")),
        "",
        "IP location is an estimate, not GPS and not a street address. This is the only email for this visit.",
    ]
    return "\n".join(lines)


def _line(label: str, value) -> str:
    text = "Unavailable" if value is None or value == "" else str(value)
    return f"{label}: {text}"


def _joined(name, version) -> str | None:
    parts = [part for part in (name, version) if part]
    return " ".join(parts) or None


def _coordinates(latitude, longitude) -> str | None:
    if latitude is None or longitude is None:
        return None
    return f"{latitude}, {longitude}"


def _place(summary: dict) -> str:
    parts = [summary.get("city"), summary.get("region"), summary.get("country")]
    text = ", ".join(part for part in parts if part)
    return text or "Unavailable"


def _format_time(value: str | None, timezone_name: str) -> str | None:
    if not value:
        return None
    try:
        moment = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=ZoneInfo("UTC"))
    except ValueError:
        return value
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        zone = ZoneInfo("UTC")
    return moment.astimezone(zone).strftime("%d %b %Y, %I:%M %p %Z")


def _recipient() -> str:
    return os.environ.get("VISITOR_NOTIFY_EMAIL", DEFAULT_EMAIL).strip() or DEFAULT_EMAIL


def _api_key() -> str:
    return os.environ.get("RESEND_API_KEY", "").strip()

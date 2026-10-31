"""Request metadata: client IP, user agent, and IP geolocation.

IP coordinates are always labeled as estimates. Nothing here is GPS.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import urllib.error
import urllib.request
from typing import Mapping

NOTICE_VERSION = "2026-10-31"

_PRIVATE_HINTS = ("local", "private", "loopback")


def extract_ip(
    remote_addr: str | None,
    headers: Mapping[str, str],
    *,
    on_vercel: bool,
    trust_proxy: bool,
) -> str:
    """Return the client IP from trusted platform metadata only.

    Arbitrary X-Forwarded-For values are ignored unless the app is actually
    behind Vercel or TRUST_PROXY=1.
    """
    if on_vercel:
        for key in ("x-vercel-forwarded-for", "x-real-ip", "x-forwarded-for"):
            found = _first_public_or_any(_header(headers, key))
            if found:
                return found
    elif trust_proxy:
        found = _first_public_or_any(_header(headers, "x-forwarded-for"))
        if found:
            return found
    return (remote_addr or "").strip()


def _header(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name:
            return value or ""
    return ""


def _first_public_or_any(value: str) -> str:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        return ""
    for part in parts:
        if _ip_or_none(part) and not _is_local(part):
            return part
    return parts[0]


def _ip_or_none(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _is_local(value: str) -> bool:
    parsed = _ip_or_none(value)
    if parsed is None:
        return True
    return bool(
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_reserved
        or parsed.is_link_local
        or parsed.is_multicast
    )


def ip_version(value: str) -> str | None:
    parsed = _ip_or_none(value)
    if parsed is None:
        return None
    return "ipv6" if parsed.version == 6 else "ipv4"


def lookup_ip(ip: str) -> dict:
    """Approximate network location. Missing fields stay null — never invented."""
    base = {
        "ip_address": ip or None,
        "ip_version": ip_version(ip) if ip else None,
        "country": None,
        "region": None,
        "city": None,
        "isp": None,
        "asn": None,
        "organization": None,
        "latitude": None,
        "longitude": None,
        "provider": "unavailable",
        "source_label": "IP estimated location",
    }
    if not ip or _is_local(ip):
        base["provider"] = "local"
        return base

    provider = os.environ.get("IPGEO_PROVIDER", "ipwho").strip().lower()
    if provider in ("", "none", "off"):
        base["provider"] = "none"
        return base

    cached = _cache_get(ip)
    if cached:
        return cached

    try:
        if provider == "ipinfo":
            record = _lookup_ipinfo(ip)
        else:
            record = _lookup_ipwho(ip)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, OSError):
        base["provider"] = "unavailable"
        return base

    record["source_label"] = "IP estimated location"
    _cache_put(ip, record)
    return record


def _lookup_ipwho(ip: str) -> dict:
    url = "https://ipwho.is/" + urllib.request.quote(ip)
    payload = _get_json(url)
    if not payload.get("success"):
        raise ValueError("ipwho lookup failed")
    connection = payload.get("connection") or {}
    asn = connection.get("asn")
    asn_text = f"AS{asn}" if isinstance(asn, int) else (str(asn) if asn else None)
    return _clean_geo(
        ip,
        provider="ipwho",
        country=_text(payload.get("country")),
        region=_text(payload.get("region")),
        city=_text(payload.get("city")),
        isp=_text(connection.get("isp")),
        asn=asn_text,
        organization=_text(connection.get("org")),
        latitude=_coord(payload.get("latitude")),
        longitude=_coord(payload.get("longitude")),
    )


def _lookup_ipinfo(ip: str) -> dict:
    token = os.environ.get("IPINFO_TOKEN", "").strip()
    if not token:
        raise ValueError("IPINFO_TOKEN missing")
    url = "https://ipinfo.io/" + urllib.request.quote(ip) + "/json?token=" + urllib.request.quote(token)
    payload = _get_json(url)
    lat = lng = None
    loc = payload.get("loc") or ""
    if isinstance(loc, str) and "," in loc:
        raw_lat, raw_lng = loc.split(",", 1)
        lat, lng = _coord(raw_lat), _coord(raw_lng)
    org = _text(payload.get("org"))
    asn = None
    organization = org
    if org and org.upper().startswith("AS"):
        parts = org.split(" ", 1)
        asn = parts[0]
        organization = parts[1] if len(parts) > 1 else org
    return _clean_geo(
        ip,
        provider="ipinfo",
        country=_text(payload.get("country")),
        region=_text(payload.get("region")),
        city=_text(payload.get("city")),
        isp=organization,
        asn=asn,
        organization=organization,
        latitude=lat,
        longitude=lng,
    )


def _clean_geo(ip: str, **fields) -> dict:
    record = {
        "ip_address": ip,
        "ip_version": ip_version(ip),
        "country": fields.get("country"),
        "region": fields.get("region"),
        "city": fields.get("city"),
        "isp": fields.get("isp"),
        "asn": fields.get("asn"),
        "organization": fields.get("organization"),
        "latitude": fields.get("latitude"),
        "longitude": fields.get("longitude"),
        "provider": fields.get("provider") or "unavailable",
        "source_label": "IP estimated location",
    }
    return record


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "portfolio-visitor-intel", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=2.0) as response:
        return json.loads(response.read().decode("utf-8"))


def _text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in _PRIVATE_HINTS:
        return None
    return text[:160]


def _coord(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return round(number, 6)


_IP_CACHE: dict[str, dict] = {}


def _cache_get(ip: str) -> dict | None:
    return _IP_CACHE.get(ip)


def _cache_put(ip: str, record: dict) -> None:
    if len(_IP_CACHE) > 512:
        _IP_CACHE.clear()
    _IP_CACHE[ip] = record


_BROWSER_RULES = (
    ("Edge", r"Edg/([0-9.]+)"),
    ("Chrome", r"Chrome/([0-9.]+)"),
    ("Firefox", r"Firefox/([0-9.]+)"),
    ("Safari", r"Version/([0-9.]+).*Safari/"),
)


def parse_user_agent(user_agent: str | None) -> dict:
    """Coarse device labels from the user-agent string. No fingerprint hash."""
    ua = (user_agent or "").strip()
    browser = "Other"
    browser_version = None
    if ua:
        for name, pattern in _BROWSER_RULES:
            match = re.search(pattern, ua)
            if match and not (name == "Chrome" and "Edg/" in ua):
                browser = name
                browser_version = match.group(1)[:32]
                break
        if "Edg/" in ua:
            match = re.search(r"Edg/([0-9.]+)", ua)
            browser = "Edge"
            browser_version = match.group(1)[:32] if match else None

    os_name = None
    os_version = None
    device_type = "desktop"
    device_model = None
    if not ua:
        device_type = None
    else:
        if re.search(r"iPad|Tablet", ua):
            device_type = "tablet"
        elif re.search(r"Mobi|iPhone|Android", ua):
            device_type = "mobile"
        if "iPhone" in ua:
            os_name = "iOS"
            device_model = "iPhone"
            device_type = "mobile"
        elif "iPad" in ua:
            os_name = "iOS"
            device_model = "iPad"
            device_type = "tablet"
        elif "Android" in ua:
            os_name = "Android"
            match = re.search(r"Android ([0-9.]+)", ua)
            os_version = match.group(1)[:32] if match else None
        elif "Windows NT" in ua:
            os_name = "Windows"
            match = re.search(r"Windows NT ([0-9.]+)", ua)
            os_version = match.group(1)[:32] if match else None
        elif "Mac OS X" in ua:
            os_name = "macOS"
            match = re.search(r"Mac OS X ([0-9_]+)", ua)
            if match:
                os_version = match.group(1).replace("_", ".")[:32]
        elif "Linux" in ua:
            os_name = "Linux"

    return {
        "device_type": device_type,
        "device_model": device_model,
        "browser": browser if ua else None,
        "browser_version": browser_version,
        "os_name": os_name,
        "os_version": os_version,
        "user_agent": ua[:400] if ua else None,
    }


def clean_metric(value, *, pattern: str, limit: int = 32) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not re.fullmatch(pattern, value):
        return None
    return value[:limit]


def clean_label(value, limit: int = 80) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().replace("\n", " ").replace("\r", "")
    if not value:
        return None
    return value[:limit]


def clean_path(value) -> str:
    if not isinstance(value, str):
        return "/"
    value = value.strip()
    if not value.startswith("/") or value.startswith("//") or "\n" in value or "\r" in value or "\x00" in value:
        return "/"
    return value[:300]

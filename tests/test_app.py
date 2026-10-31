"""Basic route and content checks for the portfolio app."""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["VISITOR_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "visitors.db")
os.environ["VISITOR_ADMIN_PASSWORD"] = "test-admin-password"
os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
os.environ["IPGEO_PROVIDER"] = "none"
os.environ["RESEND_API_KEY"] = ""
os.environ.pop("VERCEL", None)
os.environ.pop("TRUST_PROXY", None)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402
import content  # noqa: E402


def unlock(client, *, lat=12.9716, lng=77.5946, forwarded_for=None):
    headers = {}
    if forwarded_for:
        headers["X-Forwarded-For"] = forwarded_for
    page = client.get("/", headers=headers)
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Allow to continue" in html
    assert "is-locked" in html
    assert "site-preview" in html
    assert "Production Status Dashboard" in html
    match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    assert match
    response = client.post(
        "/api/access/location",
        json={
            "latitude": lat,
            "longitude": lng,
            "accuracy": 18,
            "timestamp": 1_730_000_000_000,
            "timezone": "Asia/Kolkata",
            "language": "en-IN",
            "screen": "390x844",
            "viewport": "390x700",
            "ip": "203.0.113.50",
        },
        headers={"X-CSRF-Token": match.group(1), **headers},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["unlocked"] is True
    return match.group(1)


def login_admin(client):
    page = client.get("/admin/login")
    token = re.search(r'name="csrf" value="([^"]+)"', page.get_data(as_text=True)).group(1)
    response = client.post("/admin/login", data={"csrf": token, "password": "test-admin-password"})
    assert response.status_code == 302


def test_experience_years_from_career_start():
    assert content.CAREER_START == date(2023, 8, 3)
    assert content.years_of_experience(date(2023, 8, 2)) == 0
    assert content.years_of_experience(date(2023, 8, 3)) == 0
    assert content.years_of_experience(date(2024, 8, 2)) == 0
    assert content.years_of_experience(date(2024, 8, 3)) == 1
    assert content.years_of_experience(date(2026, 8, 2)) == 2
    assert content.years_of_experience(date(2026, 8, 3)) == 3
    assert content.years_of_experience(date(2026, 10, 19)) == 3
    assert content.experience_label(date(2026, 10, 19)) == "3+ years"
    about = content.get_profile(date(2026, 10, 19))["about"]
    assert "3+ years of experience" in about


def test_home_ok():
    client = app.test_client()
    unlock(client)
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    profile = content.get_profile()
    assert profile["name"] in html or profile["short_name"] in html
    assert f"{profile['experience_label']} of experience" in html
    assert "Explore My Work" in html
    assert "Production Status Dashboard" in html
    assert profile["portrait"] in html
    assert "village-landscape" in html
    assert "7995551276" not in html
    assert "/images/certificates/azure-fundamentals.jpg" in html
    assert "/images/achievements/vtu-central-zone-kabaddi.jpg" in html
    assert "Also listed on resume" in html
    assert "More documents on file" in html
    assert "source document not attached" not in html
    assert "Download Resume" in html


def test_project_pages():
    client = app.test_client()
    unlock(client)
    for project in content.PROJECTS:
        response = client.get(f"/projects/{project['slug']}/")
        assert response.status_code == 200, project["slug"]
        html = response.get_data(as_text=True)
        assert project["title"].split("&")[0].strip() in html


def test_unknown_project_404():
    client = app.test_client()
    unlock(client)
    response = client.get("/projects/does-not-exist/")
    assert response.status_code == 404


def test_assets_present():
    assert (ROOT / "private" / "resume.pdf").is_file()
    assert (ROOT / "public" / "images" / "portrait" / "anudeep-portrait.jpg").is_file()
    assert (ROOT / "private" / "certificates" / "azure-fundamentals.pdf").is_file()
    assert (ROOT / "private" / "certificates" / "oracle-ai-certificate.pdf").is_file()
    assert (ROOT / "public" / "images" / "achievements" / "vtu-central-zone-kabaddi.jpg").is_file()
    assert (ROOT / "public" / "images" / "hero" / "village-landscape.jpg").is_file()
    assert (ROOT / "public" / "images" / "hero" / "village-landscape-sm.jpg").is_file()


def test_no_duplicate_prodvision_name():
    titles = [p["title"].lower() for p in content.PROJECTS]
    assert sum("prodvision" in t for t in titles) == 0
    assert sum("production status dashboard" in t for t in titles) == 1


def test_gate_blocks_documents_until_gps():
    client = app.test_client()
    home = client.get("/")
    assert "Allow to continue" in home.get_data(as_text=True)
    resume = client.get("/resume.pdf")
    assert resume.status_code == 401
    assert b"%PDF" not in resume.data
    cert = client.get("/certificates/azure-fundamentals.pdf")
    assert cert.status_code == 401
    assert b"%PDF" not in cert.data
    assert client.get("/admin/api/overview").status_code == 401


def test_denied_permission_stays_locked():
    client = app.test_client()
    page = client.get("/")
    token = re.search(r'name="csrf-token" content="([^"]+)"', page.get_data(as_text=True)).group(1)
    outcome = client.post(
        "/api/access/outcome",
        json={"status": "denied"},
        headers={"X-CSRF-Token": token},
    )
    assert outcome.status_code == 200
    assert outcome.get_json()["unlocked"] is False
    again = client.get("/")
    assert "Allow to continue" in again.get_data(as_text=True)
    assert "is-locked" in again.get_data(as_text=True)


def test_bad_location_and_csrf_do_not_unlock():
    client = app.test_client()
    page = client.get("/")
    token = re.search(r'name="csrf-token" content="([^"]+)"', page.get_data(as_text=True)).group(1)
    bad = client.post(
        "/api/access/location",
        json={"latitude": 91, "longitude": 0, "accuracy": 10, "timestamp": 1_730_000_000_000},
        headers={"X-CSRF-Token": token},
    )
    assert bad.status_code == 400
    forged = client.post(
        "/api/access/location",
        json={"latitude": 12.9, "longitude": 77.5, "accuracy": 10, "timestamp": 1_730_000_000_000},
        headers={"X-CSRF-Token": "not-the-token"},
    )
    assert forged.status_code == 403
    still_locked = client.get("/").get_data(as_text=True)
    assert "Allow to continue" in still_locked
    assert "is-locked" in still_locked


def test_client_ip_is_not_taken_from_the_browser():
    from visitor_intel.net import extract_ip

    assert extract_ip("127.0.0.1", {"X-Forwarded-For": "203.0.113.8"}, on_vercel=False, trust_proxy=False) == "127.0.0.1"
    assert extract_ip("10.0.0.1", {"X-Vercel-Forwarded-For": "203.0.113.9"}, on_vercel=True, trust_proxy=False) == "203.0.113.9"

    client = app.test_client()
    unlock(client, forwarded_for="203.0.113.8")
    login_admin(client)
    listed = client.get("/admin/api/visitors").get_json()
    assert listed["rows"]
    assert all(row["ip_address"] == "127.0.0.1" for row in listed["rows"] if row["visitor_id"])
    match = None
    for row in listed["rows"]:
        detail = client.get("/admin/api/visitors/" + row["visitor_id"]).get_json()
        gps = (detail["sessions"][0].get("gps") or {})
        if gps.get("maps_url") == "https://www.google.com/maps/search/?api=1&query=12.9716,77.5946":
            match = detail
            break
    assert match is not None
    assert match["sessions"][0]["gps"]["source_label"] == "GPS verified location"
    assert match["sessions"][0]["ip"]["source_label"] == "IP estimated location"
    assert match["sessions"][0]["ip"]["ip_address"] == "127.0.0.1"
    assert client.get("/admin/api/map").status_code == 404
    page = client.get("/admin")
    assert "Visitor map" not in page.get_data(as_text=True)
    assert "leaflet" not in page.get_data(as_text=True).lower()


def test_resume_downloads_after_grant_and_admin_can_revoke():
    client = app.test_client()
    unlock(client)
    resume = client.get("/resume.pdf")
    assert resume.status_code == 200
    assert resume.data.startswith(b"%PDF")
    assert resume.headers["Content-Disposition"].startswith("attachment")
    certificate = client.get("/certificates/azure-fundamentals.pdf")
    assert certificate.status_code == 200
    assert certificate.data.startswith(b"%PDF")
    assert certificate.headers["Content-Disposition"].startswith("inline")
    from itsdangerous import URLSafeTimedSerializer

    cookie = client.get_cookie("pv_s")
    session_id = URLSafeTimedSerializer("test-secret-key", salt="pv-visitor-v1").loads(cookie.value)["k"]
    login_admin(client)
    revoked = client.post(
        f"/admin/api/sessions/{session_id}/revoke",
        headers={"X-Requested-With": "fetch"},
    )
    assert revoked.status_code == 200
    locked = client.get("/")
    assert "Allow to continue" in locked.get_data(as_text=True)


def test_first_grant_prepares_one_visit_email(monkeypatch):
    sent = []

    def capture(message):
        sent.append(message)

    monkeypatch.setattr("visitor_intel.notify.deliver", capture)
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("VISITOR_NOTIFY_EMAIL", "owner@example.com")
    client = app.test_client()
    token = unlock(client)
    assert len(sent) == 1
    message = sent[0]
    assert message["to"] == ["owner@example.com"]
    text = message["text"]
    assert "GPS verified location" in text
    assert "IP estimated location" in text
    assert "12.9716, 77.5946" in text
    assert text.count("https://www.google.com/maps/search/?api=1&query=12.9716,77.5946") == 1
    assert "Accuracy: 18 m" in text
    assert "Language: en-IN" in text
    assert "Screen: 390x844" in text
    assert "Viewport: 390x700" in text
    assert "Time zone: Asia/Kolkata" in text
    assert "203.0.113.50" not in text
    assert "127.0.0.1" in text
    again = client.post(
        "/api/access/location",
        json={
            "latitude": 12.9716,
            "longitude": 77.5946,
            "accuracy": 18,
            "timestamp": 1_730_000_000_000,
        },
        headers={"X-CSRF-Token": token},
    )
    assert again.status_code == 200
    assert again.get_json()["unlocked"] is True
    assert len(sent) == 1


def test_visit_email_is_skipped_without_api_key(monkeypatch):
    called = []
    monkeypatch.setattr("visitor_intel.notify.deliver", lambda message: called.append(message))
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    client = app.test_client()
    unlock(client)
    assert called == []

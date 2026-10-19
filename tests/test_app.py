"""Basic route and content checks for the portfolio app."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402
import content  # noqa: E402


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
    for project in content.PROJECTS:
        response = client.get(f"/projects/{project['slug']}/")
        assert response.status_code == 200, project["slug"]
        html = response.get_data(as_text=True)
        assert project["title"].split("&")[0].strip() in html


def test_unknown_project_404():
    client = app.test_client()
    response = client.get("/projects/does-not-exist/")
    assert response.status_code == 404


def test_assets_present():
    assert (ROOT / "public" / "resume.pdf").is_file()
    assert (ROOT / "public" / "images" / "portrait" / "anudeep-portrait.jpg").is_file()
    assert (ROOT / "public" / "certificates" / "azure-fundamentals.pdf").is_file()
    assert (ROOT / "public" / "certificates" / "oracle-ai-certificate.pdf").is_file()
    assert (ROOT / "public" / "images" / "achievements" / "vtu-central-zone-kabaddi.jpg").is_file()
    assert (ROOT / "public" / "images" / "hero" / "village-landscape.jpg").is_file()
    assert (ROOT / "public" / "images" / "hero" / "village-landscape-sm.jpg").is_file()


def test_no_duplicate_prodvision_name():
    titles = [p["title"].lower() for p in content.PROJECTS]
    assert sum("prodvision" in t for t in titles) == 0
    assert sum("production status dashboard" in t for t in titles) == 1

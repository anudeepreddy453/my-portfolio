"""Flask portfolio application for Pulikunta Anudeep Kumar Reddy."""

from __future__ import annotations

import os
import re
from datetime import timedelta
from pathlib import Path

from flask import Flask, abort, g, make_response, render_template, request, send_file

import content
from visitor_intel.access import apply_cookies, attach, locked_response, render_gate
from visitor_intel.routes import bp as visitor_bp

ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT / "private"


def _load_env() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_env()

app = Flask(
    __name__,
    template_folder="templates",
    # Locally Flask serves files from public/ at the site root.
    # On Vercel, public/** is served by the CDN before this app.
    static_folder="public",
    static_url_path="",
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "local-dev-only-change-me"
app.config.update(
    SESSION_COOKIE_NAME="pv_admin",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=os.environ.get("VERCEL") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=64 * 1024,
)
app.register_blueprint(visitor_bp)


def _portfolio_path(path: str) -> bool:
    if path in {"/", "/resume.pdf"}:
        return True
    if path.startswith("/projects/"):
        return True
    return path.startswith("/certificates/") and path.endswith(".pdf")


@app.before_request
def _open_visitor_session():
    if _portfolio_path(request.path):
        attach(create=True)


@app.after_request
def _protect_response(response):
    apply_cookies(response)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "geolocation=(self)")
    content_type = response.content_type or ""
    if "text/html" in content_type or request.path == "/resume.pdf" or request.path.startswith("/certificates/"):
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Cookie"
    return response


@app.context_processor
def inject_globals():
    return {
        "profile": content.get_profile(),
        "nav_items": [
            ("About", "/#about"),
            ("Experience", "/#experience"),
            ("Projects", "/#projects"),
            ("Skills", "/#skills"),
            ("Credentials", "/#credentials"),
            ("Contact", "/#contact"),
        ],
        "track_visit": bool(getattr(g, "access_granted", False)),
        "csrf_token": getattr(g, "csrf_token", ""),
    }


def _home_context() -> dict:
    return {
        "experience": content.EXPERIENCE,
        "projects": content.PROJECTS,
        "skills": content.SKILLS,
        "education": content.EDUCATION,
        "certifications": content.CERTIFICATIONS,
        "additional_documents": content.ADDITIONAL_DOCUMENTS,
        "achievements": content.ACHIEVEMENTS,
        "publication": content.PUBLICATION,
        "languages": content.LANGUAGES,
        "interests": content.INTERESTS,
    }


def _locked_page(status: int = 200):
    response = make_response(
        render_template(
            "index.html",
            locked=True,
            rate_limited=bool(getattr(g, "rate_limited", False)),
            **_home_context(),
        ),
        status,
    )
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Permissions-Policy"] = "geolocation=(self)"
    return response


render_gate.page = _locked_page


@app.route("/")
def index():
    blocked = locked_response()
    if blocked:
        return blocked
    return render_template("index.html", **_home_context())


@app.route("/projects/<slug>/")
def project_detail(slug: str):
    blocked = locked_response()
    if blocked:
        return blocked
    project = content.get_project(slug)
    if project is None:
        abort(404)
    return render_template("project.html", project=project)


@app.route("/resume.pdf")
def resume_pdf():
    blocked = locked_response(401)
    if blocked:
        return blocked
    path = PRIVATE / "resume.pdf"
    if not path.is_file():
        abort(404)
    return send_file(
        path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="Anudeep-Reddy-Resume.pdf",
        max_age=0,
    )


@app.route("/certificates/<name>.pdf")
def certificate_pdf(name: str):
    if not re.fullmatch(r"[a-z0-9-]+", name):
        abort(404)
    blocked = locked_response(401)
    if blocked:
        return blocked
    root = (PRIVATE / "certificates").resolve()
    path = (root / f"{name}.pdf").resolve()
    if path.parent != root or not path.is_file():
        abort(404)
    return send_file(
        path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=path.name,
        max_age=0,
    )


@app.errorhandler(404)
def not_found(_error):
    path = request.path
    if path.startswith(("/css/", "/js/", "/images/")) or path == "/favicon.svg":
        return "Not found", 404
    if path.startswith("/admin") or path.startswith("/api/"):
        return "Not found", 404
    if not getattr(g, "visitor_attached", False):
        attach(create=True)
    blocked = locked_response()
    if blocked:
        return blocked
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True, port=5000)

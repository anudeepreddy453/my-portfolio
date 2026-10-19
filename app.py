"""Flask portfolio application for Pulikunta Anudeep Kumar Reddy."""

from __future__ import annotations

from flask import Flask, abort, render_template

import content

app = Flask(
    __name__,
    template_folder="templates",
    # Locally Flask serves files from public/ at the site root.
    # On Vercel, public/** is served by the CDN.
    static_folder="public",
    static_url_path="",
)


@app.context_processor
def inject_globals():
    return {
        "profile": content.PROFILE,
        "nav_items": [
            ("About", "/#about"),
            ("Experience", "/#experience"),
            ("Projects", "/#projects"),
            ("Skills", "/#skills"),
            ("Credentials", "/#credentials"),
            ("Contact", "/#contact"),
        ],
    }


@app.route("/")
def index():
    return render_template(
        "index.html",
        experience=content.EXPERIENCE,
        projects=content.PROJECTS,
        skills=content.SKILLS,
        education=content.EDUCATION,
        certifications=content.CERTIFICATIONS,
        additional_documents=content.ADDITIONAL_DOCUMENTS,
        achievements=content.ACHIEVEMENTS,
        publication=content.PUBLICATION,
        languages=content.LANGUAGES,
        interests=content.INTERESTS,
    )


@app.route("/projects/<slug>/")
def project_detail(slug: str):
    project = content.get_project(slug)
    if project is None:
        abort(404)
    return render_template("project.html", project=project)


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True, port=5000)

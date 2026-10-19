"""Portfolio content — single source of truth for templates."""

from __future__ import annotations

from datetime import date

# Professional journey start — experience years are derived from this date.
CAREER_START = date(2023, 8, 3)


def years_of_experience(as_of: date | None = None) -> int:
    """Completed full years since CAREER_START (never negative)."""
    today = as_of or date.today()
    years = today.year - CAREER_START.year
    if (today.month, today.day) < (CAREER_START.month, CAREER_START.day):
        years -= 1
    return max(years, 0)


def experience_label(as_of: date | None = None) -> str:
    """Recruiter-style label, e.g. '3+ years'."""
    return f"{years_of_experience(as_of)}+ years"


def get_profile(as_of: date | None = None) -> dict:
    """Profile dict with experience text computed from CAREER_START."""
    label = experience_label(as_of)
    return {
        "name": "Pulikunta Anudeep Kumar Reddy",
        "short_name": "Anudeep Reddy",
        "headline": (
            "Software Engineer | Python Development | Production Automation "
            "| Data Dashboards | AI Integration"
        ),
        "location": "Bengaluru, India",
        "hero_location": "Pulikunta",
        "hero_maps_url": (
            "https://www.google.com/maps/dir/?api=1"
            "&destination=Pulikunta,+Andhra+Pradesh+516267"
        ),
        "email": "anudeepreddy453@gmail.com",
        "linkedin": "https://www.linkedin.com/in/anudeepreddy-pulikunta/",
        "resume_path": "/resume.pdf",
        "portrait": "/images/portrait/anudeep-portrait.jpg",
        "portrait_alt": "Portrait of Pulikunta Anudeep Kumar Reddy",
        "hero_image": "/images/hero/village-landscape.jpg",
        "hero_image_sm": "/images/hero/village-landscape-sm.jpg",
        "hero_image_alt": (
            "Countryside landscape photograph of Anudeep Reddy’s village, "
            "taken by the author"
        ),
        "hero_title": (
            "Building reliable Python systems, production dashboards, "
            "and AI-assisted engineering workflows."
        ),
        "hero_strengths": (
            "Python · Flask · production automation · operational dashboards · "
            "SQL · AI / LLM evaluation"
        ),
        "years_experience": years_of_experience(as_of),
        "experience_label": label,
        "about": (
            f"Software Engineer with {label} of experience building Python "
            "applications, production automation, and operational dashboards. "
            "Based in Bengaluru, I turn manual workflows into maintainable "
            "systems—covering data processing, production monitoring, REST "
            "integrations, and practical AI/LLM evaluation in engineering work. "
            "Outside delivery I stay curious about AI tooling, chess, and sports."
        ),
        "highlights": [
            f"{label} software engineering",
            "Python & backend systems",
            "AI / LLM evaluation",
        ],
    }


# Default snapshot for imports/tests that expect a PROFILE mapping.
PROFILE = get_profile()

EXPERIENCE = [
    {
        "company": "Société Générale Global Solutions",
        "role": "Software Engineer",
        "location": "Bengaluru, India",
        "period": "August 2023 – Present",
        "bullets": [
            "Develop Python applications that automate operational workflows and repetitive tasks.",
            "Build Flask- and Dash-based dashboards for production visibility, job execution, logs, and operational metrics.",
            "Automate data extraction, transformation, validation, and reporting with Python and SQL.",
            "Integrate REST APIs and backend services into dashboards and production workflows.",
            "Monitor production jobs and investigate failures and operational issues.",
            "Improve reliability, maintainability, and performance in Python and SQL workflows.",
            "Explore practical AI integration in engineering and production workflows.",
        ],
    },
    {
        "company": "Turing",
        "role": "AI Trainer & Large Language Model Evaluator",
        "location": "Remote",
        "period": "Part-time · Contract",
        "bullets": [
            "Evaluate AI coding agents and long-horizon software engineering tasks.",
            "Assess GLM-5.2-generated solutions against functional requirements using multi-trial testing and regression analysis.",
            "Validate AI-generated code through smoke tests, security checks, and quality workflows.",
            "Use Python, Cursor, Cline, and VS Code in AI-assisted engineering workflows.",
            "Apply test-driven development and CI/CD quality practices where appropriate.",
        ],
    },
]

PROJECTS = [
    {
        "slug": "production-status-dashboard",
        "title": "Production Status Dashboard",
        "subtitle": "Formerly ProdVision · consolidates CCR production tracking",
        "summary": (
            "A Flask application that consolidates production monitoring and "
            "reporting across supported applications—replacing fragmented "
            "spreadsheet tracking with searchable statuses, structured issues, "
            "period reports, and controlled Excel imports. Related work extends "
            "batch monitoring with log processing and ML/NLP-assisted anomaly signals."
        ),
        "purpose": (
            "Operations teams needed one place to track daily production "
            "status, issues, and period reporting instead of scattered Excel "
            "files. This dashboard centralizes that work with authorization, "
            "auditability, and exportable reports."
        ),
        "features": [
            "Production monitoring across supported applications such as CVAR ALL, CVAR NYQ, XVA, and REG",
            "Daily production statuses, operational issues, and PRB/HIIM tracking",
            "Search, filtering, sorting, pagination, date-range selection, and expandable issue details",
            "Monthly, quarterly, half-yearly, yearly, and custom-period reporting",
            "Excel and CSV exports for operational reviews",
            "Administrator-controlled Excel migration with column mapping, validation, previews, duplicate handling, and transactional imports",
            "Role-based authorization, CSRF protection, password hashing, audit logs, and backups",
            "Separate SQLite databases per supported application, as designed",
            "Automated testing with pytest",
        ],
        "ai_extension": {
            "title": "Related: AI-assisted batch monitoring",
            "summary": (
                "Complementary Python, Flask, and Dash work for CVAR batch "
                "workflows includes automated log processing, operational "
                "dashboards, ML/NLP-assisted anomaly detection, time-series "
                "trend analysis, batch ETA support, and alerting. Presented "
                "here as related monitoring work rather than a separate product."
            ),
            "features": [
                "Automated production log processing for batch workflow visibility",
                "Interactive operational dashboards with Flask and Dash",
                "Machine learning and NLP-assisted anomaly detection for abnormal execution patterns",
                "Time-series and historical trend analysis with batch ETA support",
                "Automated alerts to accelerate issue identification",
            ],
        },
        "engineering_value": (
            "Consolidating production tracking into a structured application "
            "reduces manual rework during period-end reviews, improves "
            "traceability of issues, and gives teams a maintainable path to "
            "extend reporting without reinventing spreadsheets each cycle."
        ),
        "tech": [
            "Python",
            "Flask",
            "Dash",
            "SQLAlchemy Core",
            "SQLite",
            "HTML",
            "CSS",
            "JavaScript",
            "Chart.js",
            "Pandas",
            "openpyxl",
            "pytest",
        ],
        "preview": "dashboard",
        "featured": True,
        "illustration_note": "Illustrative demo with synthetic sample data — not a production screenshot.",
    },
    {
        "slug": "ganesha-festival-platform",
        "title": "Ganesha Festival Management Platform",
        "subtitle": "Full-stack community operations for multi-village festivals",
        "summary": (
            "A practical Flask platform for festival organizers: village-scoped "
            "data, media, donations and expenses, events, auctions, and "
            "role-based administration with auditability."
        ),
        "purpose": (
            "Community festival teams need reliable records across years and "
            "villages—finances, media, schedules, and access control—without "
            "depending on ad-hoc spreadsheets or shared drives alone."
        ),
        "features": [
            "Multi-village data isolation and festival-year history",
            "Community media gallery with uploads, thumbnails, moderation, and access controls",
            "Donations, expenses, receipts, and in-kind contributions",
            "Events and schedules",
            "Laddu auctions with bid validation",
            "Financial summaries for organizers",
            "Registration and email verification",
            "Role-based access, audit logs, and login history",
            "Database migrations, backups, and restoration",
            "Responsive layout with installable web-app capabilities",
        ],
        "engineering_value": (
            "Demonstrates end-to-end Python backend development: multi-tenant "
            "data boundaries, secure auth, financial and media workflows, and "
            "operational tooling (migrations, backups) for a real community use case."
        ),
        "tech": [
            "Python 3.11",
            "Flask 3.1",
            "SQLAlchemy 2",
            "Flask-SQLAlchemy",
            "SQLite",
            "PostgreSQL (supported)",
            "HTML",
            "CSS",
            "JavaScript",
        ],
        "preview": "festival",
        "featured": True,
        "illustration_note": "Illustrative demo with synthetic sample records — not live community data.",
        "note": (
            "A public live demo is omitted to avoid exposing private "
            "community records or administrator functionality."
        ),
    },
    {
        "slug": "data-processing-reporting",
        "title": "Data Processing & Reporting System",
        "subtitle": "Python, SQL, and PySpark data preparation",
        "summary": (
            "A data processing workflow using Python, SQL, and PySpark to "
            "extract, transform, validate, and prepare multi-source enterprise "
            "datasets for analytics and reporting."
        ),
        "purpose": (
            "Downstream analytics depends on consistent, validated datasets. "
            "This work focused on reliable extraction, transformation, and "
            "reporting-ready outputs from multiple sources."
        ),
        "features": [
            "Multi-source data extraction and preparation",
            "Transformation and validation for analytics-ready datasets",
            "Python and SQL processing with PySpark where needed",
            "Reporting-oriented outputs for downstream consumers",
        ],
        "engineering_value": (
            "Shows disciplined data engineering habits: clear transforms, "
            "validation, and reproducible processing paths rather than "
            "one-off spreadsheet cleanup."
        ),
        "tech": ["Python", "SQL", "PySpark", "Pandas"],
        "preview": "data",
        "featured": True,
        "illustration_note": "Illustrative pipeline diagram — synthetic labels only.",
    },
]

SKILLS = {
    "Programming": ["Python", "SQL"],
    "Backend development": ["Flask", "FastAPI", "REST APIs", "Dash"],
    "Data processing": ["Pandas", "PySpark"],
    "Databases": ["SQLite", "PostgreSQL"],
    "Automation and systems": [
        "Linux/Unix",
        "Production monitoring",
        "Workflow automation",
        "Git",
    ],
    "AI and LLM evaluation": [
        "LLM evaluation",
        "AI-assisted software engineering",
        "AI integration",
        "Machine learning",
        "NLP",
    ],
    "Testing and practices": ["Testing", "CI/CD", "HTML", "CSS"],
}

EDUCATION = {
    "school": "New Horizon College of Engineering",
    "degree": "Bachelor of Engineering — Electronics and Communication Engineering",
    "location": "Bengaluru, India",
    "period": "2019–2023",
    "cgpa": "8.07/10",
}

# Resume-listed certifications. Attach preview/document only when verified on disk.
CERTIFICATIONS = [
    {
        "name": "Microsoft Certified: Azure Fundamentals",
        "issuer": "Microsoft",
        "detail": "Earned 10 April 2026 · Credential ID D11636BACF8B949",
        "has_document": True,
        "preview": "/images/certificates/azure-fundamentals.jpg",
        "document": "/certificates/azure-fundamentals.pdf",
    },
    {
        "name": "Generative AI with Large Language Models",
        "issuer": "DeepLearning.AI",
        "has_document": False,
    },
    {
        "name": "Machine Learning Engineering for Production (MLOps)",
        "issuer": "Coursera",
        "has_document": False,
    },
    {
        "name": "Oracle Fusion AI Agent Studio Foundations Associate",
        "issuer": "Oracle",
        "detail": "Oracle Certified Foundations Associate · 25 April 2026",
        "has_document": True,
        "preview": "/images/certificates/oracle-ai-certificate.jpg",
        "document": "/certificates/oracle-ai-certificate.pdf",
    },
    {
        "name": "IGNITE 2023 Internship Program",
        "issuer": "LTIMindtree",
        "has_document": True,
        "preview": "/images/certificates/ltimindtree-ignite.jpg",
        "document": "/certificates/ltimindtree-ignite.pdf",
    },
]

# Extra certificates / documents verified in the workspace.
ADDITIONAL_DOCUMENTS = [
    {
        "name": "Oracle Fusion AI Agent Studio — exam score report",
        "preview": "/images/certificates/oracle-ai-agent-studio.jpg",
        "document": "/certificates/oracle-ai-agent-studio.pdf",
    },
    {
        "name": "Nanotechnology in Engineering Applications — webinar",
        "preview": "/images/certificates/nanotechnology-webinar.jpg",
        "document": "/images/certificates/nanotechnology-webinar.jpg",
        "detail": "New Horizon College of Engineering · 15 July 2020",
    },
    {
        "name": "Getting Started with Enterprise-grade AI",
        "preview": "/images/certificates/enterprise-ai.jpg",
        "document": "/certificates/enterprise-ai.pdf",
    },
    {
        "name": "Getting Started with Enterprise Data Science",
        "preview": "/images/certificates/enterprise-data-science.jpg",
        "document": "/certificates/enterprise-data-science.pdf",
    },
    {
        "name": "Robotics certificate",
        "preview": "/images/certificates/robotics.jpg",
        "document": "/certificates/robotics.pdf",
    },
]

# Achievement wording follows the resume; photos are the scanned certificates.
ACHIEVEMENTS = [
    {
        "title": "VTU Central Zone Kabaddi — Winner",
        "detail": (
            "Bengaluru Central Zone · Kabaddi (Men) · "
            "14–15 Dec 2021 · HKBK College of Engineering"
        ),
        "image": "/images/achievements/vtu-central-zone-kabaddi.jpg",
        "image_alt": (
            "VTU certificate for Bengaluru Central Zone Kabaddi winners, "
            "2021–2022"
        ),
    },
    {
        "title": "VTU Inter-Zone Kabaddi — Runner-up",
        "detail": (
            "Inter-Zone Kabaddi (Men) · 16–17 Dec 2021 · "
            "Dr. T. Thimmaiah Institute of Technology, K.G.F."
        ),
        "image": "/images/achievements/vtu-inter-zone-kabaddi.jpg",
        "image_alt": (
            "VTU certificate for Inter-Zone Kabaddi tournament, 2021–2022"
        ),
    },
]

PUBLICATION = {
    "title": "A Survey on Spectrum Sensing Using Energy Detection for 4G Waveform",
    "author": "P. Anudeep Kumar Reddy",
    "venue": "IEEE Xplore",
    "url": "https://ieeexplore.ieee.org/author/37089844310",
    "url_label": "IEEE Xplore author profile",
    "preview": "/images/publication/spectrum-sensing-cover.jpg",
    "document": "/certificates/ieee-publication.pdf",
    "description": (
        "A survey covering spectrum sensing approaches that use energy "
        "detection techniques in the context of 4G waveforms."
    ),
}

LANGUAGES = ["English", "Telugu"]
INTERESTS = ["AI and emerging technologies", "Chess", "Sports"]


def get_project(slug: str):
    for project in PROJECTS:
        if project["slug"] == slug:
            return project
    return None

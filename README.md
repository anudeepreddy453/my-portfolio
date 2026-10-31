# Portfolio — Pulikunta Anudeep Kumar Reddy

Public personal portfolio (Flask + Jinja templates).

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000/

The portfolio stays closed until a visitor allows a one-time browser location reading. Declining leaves the site blurred and locked. A returning visit reopens only while the server session is still valid.

Admin dashboard: http://127.0.0.1:5000/admin

Set these in `.env` (never commit that file):

- `FLASK_SECRET_KEY`
- `VISITOR_ADMIN_PASSWORD`
- `VISITOR_SESSION_HOURS` (default 24)
- `VISITOR_GPS_RETENTION_DAYS` (default 30)
- `VISITOR_ACTIVITY_RETENTION_DAYS` (default 90)
- `VISITOR_TIMEZONE` (default `Asia/Kolkata`)
- `IPGEO_PROVIDER` (`ipwho`, `ipinfo`, or `none`)
- `IPINFO_TOKEN` when using ipinfo
- `VISITOR_DB_PATH` for a persistent SQLite file. On Vercel the default path is temporary, so visitor records there do not survive a restart.
- `RESEND_API_KEY` to email `VISITOR_NOTIFY_EMAIL` once when a visitor allows location. Leave it unset to skip email. The default sender is Resend’s onboarding address, which delivers only to the Resend account email until a domain is verified.
- `VISITOR_NOTIFY_EMAIL` (default `anudeepreddy453@gmail.com`)
- `VISITOR_NOTIFY_FROM` (default `Portfolio <onboarding@resend.dev>`)

## Deploy

Configured for Vercel via `vercel.json` and `public/` static assets.

---

**LifeOS** (family health & medical finance) is a separate application:  
`/Users/anudeepreddy/Downloads/lifeos`

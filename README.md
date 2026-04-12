# Vynfy Ledger MVP

Vynfy Ledger is a secure internal revenue and expense tracker built with Flask, SQLAlchemy, Jinja, HTMX, Alpine.js, and SQLite.

## Features

- Secure session-based authentication with email verification and password reset
- Admin and staff roles with ownership checks
- Revenue and expense workflows with approval actions
- Dashboard summaries, reports, CSV export, and reconciliation
- Audit logging for sensitive actions
- Seed data and automated tests

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
flask db upgrade
flask seed
flask run
```

## Environment

Use `.env.example` as the source of truth for required configuration.

## Notes

- Uploaded files are stored under `instance/uploads`.
- Outbound emails fall back to development outbox files under `instance/outbox` when SMTP is not configured.
- SQLite is used for MVP readiness and can be swapped for PostgreSQL later.

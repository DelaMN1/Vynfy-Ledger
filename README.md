# Vynfy Ledger

Vynfy Ledger is an internal finance operations application for tracking revenue, expenses, approvals, reconciliations, and audit activity. It is built with Flask, SQLAlchemy, Flask-Migrate, WTForms, server-rendered Jinja templates, and SQLite by default.

This README is intended to be enough for a new engineer to:

- understand what the application does
- start it locally
- configure the environment correctly
- run tests and migrations
- troubleshoot common setup problems
- contribute changes safely

## What The App Does

Vynfy Ledger supports:

- user registration and login
- email verification, password reset, and login challenges
- admin and staff roles
- revenue and expense entry workflows
- approval and reconciliation flows
- dashboard metrics and reports
- CSV exports
- audit logging
- file attachments

## Stack

- Python 3.13 recommended
- Flask
- Flask-SQLAlchemy
- Flask-Migrate / Alembic
- Flask-WTF
- Flask-Limiter
- WTForms
- argon2-cffi
- SQLite by default

## Repository Layout

```text
vynfy_ledger/
├── app/
│   ├── admin/               # admin views
│   ├── auth/                # authentication and account flows
│   ├── dashboard/           # dashboard views and aggregation
│   ├── models/              # SQLAlchemy models
│   ├── reconciliation/      # reconciliation flows
│   ├── reports/             # reporting and exports
│   ├── settings/            # admin-managed reference data
│   ├── static/              # CSS / JS
│   ├── templates/           # Jinja templates
│   ├── transactions/        # revenue and expense workflows
│   └── utils/               # shared helpers, enums, types, auth, security
├── migrations/              # Alembic migrations
├── tests/                   # pytest suite
├── .env.example             # local environment template
├── requirements.txt         # Python dependencies
└── run.py                   # local app entrypoint
```

## Prerequisites

Before you start, make sure you have:

- Python installed
- PowerShell or another shell
- Git

Recommended:

- Python 3.13
- a dedicated virtual environment for this repo

## Quick Start

From the repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m flask --app run.py db upgrade
python run.py
```

The app will start using the configuration in `.env`.

Default local URL:

```text
http://127.0.0.1:5000
```

## First-Time Local Setup

### 1. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, you can still use the venv directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

### 2. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Create your environment file

```powershell
Copy-Item .env.example .env
```

The app loads `.env` automatically through `python-dotenv`.

### 4. Apply database migrations

```powershell
python -m flask --app run.py db upgrade
```

### 5. Optionally seed demo data

By default, development config enables demo seeding, but the command still respects `ALLOW_DEMO_SEED`.

```powershell
python -m flask --app run.py seed
```

### 6. Run the app

```powershell
python run.py
```

## Running With Flask CLI

You can also use the Flask CLI instead of `run.py`:

```powershell
python -m flask --app run.py run
```

Useful commands:

```powershell
python -m flask --app run.py routes
python -m flask --app run.py shell
python -m flask --app run.py db current
python -m flask --app run.py db history
python -m flask --app run.py seed
```

## Environment Variables

Use `.env.example` as the starting point.

### Required in production

- `SECRET_KEY`
- `SECURITY_PASSWORD_SALT`
- `DATABASE_URL`

Production secrets must be unique and at least 32 characters long.

### Core application settings

- `FLASK_APP`
  Usually `run.py`
- `FLASK_ENV`
  Conventional Flask environment flag. This app also reads `APP_ENV`.
- `APP_ENV`
  App environment selection: `development`, `testing`, or `production`
- `DATABASE_URL`
  SQLAlchemy database URL. If blank, local SQLite is used.
- `COMPANY_NAME`
  Display name used in the UI

### Security and session settings

- `SECRET_KEY`
  Flask signing secret
- `SECURITY_PASSWORD_SALT`
  Salt used for token signing flows
- `ACCESS_SESSION_MINUTES`
- `SESSION_ROTATE_AFTER_MINUTES`
- `LOGIN_LOCKOUT_BASE_MINUTES`
- `MAX_LOGIN_LOCKOUT_MINUTES`
- `LOGIN_CHALLENGE_MINUTES`
- `LOGIN_CHALLENGE_MAX_ATTEMPTS`
- `MAX_FAILED_LOGINS`
- `PASSWORD_RESET_MINUTES`
- `ADMIN_STEP_UP_MINUTES`
- `WTF_CSRF_TIME_LIMIT`
  Blank or `none` means no expiration
- `FORCE_HTTPS`
- `TRUST_PROXY_COUNT`

### Feature flags

- `REGISTRATION_ENABLED`
- `ALLOW_DEMO_SEED`

### Email settings

- `MAIL_FROM`
- `SENDGRID_API_KEY`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_USE_TLS`

If email is not configured, development flows fall back to writing messages into the local outbox folder.

## Local Development Defaults

If `DATABASE_URL` is empty, the app uses:

```text
sqlite:///instance/vynfy_ledger.db
```

Other local filesystem behavior:

- uploads are stored in `instance/uploads`
- outbox emails are written to `instance/outbox`

## Database and Migrations

This project uses Flask-Migrate / Alembic.

### Apply migrations

```powershell
python -m flask --app run.py db upgrade
```

### Create a new migration

```powershell
python -m flask --app run.py db migrate -m "Describe the schema change"
```

### Downgrade one revision

```powershell
python -m flask --app run.py db downgrade
```

### Migration expectations

- commit model changes and the generated migration together
- review autogenerated migrations before committing
- do not hand-edit old historical migrations unless you have a specific reason

## Testing

Run the full suite from the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```

You can also run individual files:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_auth.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_transactions.py -q
```

### Important

Do not assume system `python` and repo `.venv` are the same interpreter. If you see errors like:

```text
ModuleNotFoundError: No module named 'flask_limiter'
```

you are almost certainly using the wrong Python environment. Use the repo venv explicitly.

## Seed Data

The app provides a seed command:

```powershell
python -m flask --app run.py seed
```

What it does:

- creates demo users
- creates example categories, accounts, and payment methods
- creates a few sample transactions

The command is intentionally blocked unless seeding is allowed by config.

## Authentication and Email Behavior

Authentication flows include:

- password-based first step
- verification code / login challenge
- email verification
- password reset

Email behavior:

- SendGrid is used if configured
- SMTP is used if configured
- if neither is available or delivery fails in development-style setups, messages are written to the outbox folder

This means many auth flows can still be tested locally without a live email provider.

## Static Files and Uploads

Attachments are validated and stored locally under:

```text
instance/uploads
```

The app enforces a maximum request size of 5 MB.

## Troubleshooting

### `ModuleNotFoundError` for Flask packages

Cause:

- dependencies are not installed in the current interpreter

Fix:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

### App starts but database tables are missing

Cause:

- migrations were not applied

Fix:

```powershell
python -m flask --app run.py db upgrade
```

### No emails are arriving locally

Expected if SMTP or SendGrid is not configured. Check:

```text
instance/outbox
```

### HTTPS redirects are interfering locally

Set in `.env`:

```text
FORCE_HTTPS=false
TRUST_PROXY_COUNT=0
```

### Tests fail under global Python

Use the project interpreter:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```

## Development Workflow

A safe default workflow for contributors:

1. Pull the latest `main`
2. Create a feature branch
3. Activate `.venv`
4. Install dependencies if needed
5. Apply migrations
6. Make code changes
7. Add or update tests
8. Run the relevant test files
9. Run the full test suite before opening a PR
10. Submit a focused PR with a clear description

## Contributing

### Branching

Use short, descriptive branch names:

- `feature/add-report-filters`
- `fix/login-challenge-expiry`
- `refactor/settings-services`

### Commit quality

Prefer clear commit messages that describe intent:

- `Fix admin approval authorization check`
- `Refactor settings create flows`
- `Add tests for reconciliation export`

### Code expectations

When contributing:

- preserve existing behavior unless the change is intentional
- prefer small, focused changes
- keep business rules in services, not templates
- keep route handlers thin
- add tests for bug fixes and workflow changes
- avoid introducing dead compatibility layers or duplicate logic
- prefer the existing enum/type/helper patterns already used in `app/utils`

### Before opening a pull request

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```

If your change affects schema:

- generate a migration
- review it
- include it in the PR

If your change affects auth, transactions, reports, settings, or reconciliation:

- add or update tests in the matching `tests/` area

### Pull request checklist

- code builds and app starts locally
- migrations apply cleanly
- relevant tests were added or updated
- full test suite passes
- no secrets were committed
- README or env docs were updated if setup changed

## Security Notes

- production requires strong `SECRET_KEY` and `SECURITY_PASSWORD_SALT`
- cookies are marked secure in production
- the app can enforce HTTPS and proxy-aware behavior
- CSRF protection is enabled outside testing
- audit logging exists for sensitive actions

Do not commit real credentials, API keys, or production database URLs.

## Suggested Local Commands

### Start the app

```powershell
.\.venv\Scripts\python.exe run.py
```

### Apply migrations

```powershell
.\.venv\Scripts\python.exe -m flask --app run.py db upgrade
```

### Seed demo data

```powershell
.\.venv\Scripts\python.exe -m flask --app run.py seed
```

### Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```

## Notes For Future Maintainers

- Use `.venv` consistently. The system interpreter may not have the repo dependencies.
- Keep `migrations/` in sync with model changes.
- If setup changes, update both `.env.example` and this README in the same PR.
- If you introduce new configuration, document the default, purpose, and whether it is required in production.

# Vynfy Ledger

Vynfy Ledger is a Flask-based internal finance operations app for tracking revenue, expenses, approvals, reporting, reconciliation, and audit activity.

The app is PostgreSQL-first for real runtime use. SQLite is used only in tests and as a legacy import source.

## What This App Does

- manages admin and staff access
- records revenue and expense activity
- supports expense submission, approval, rejection, return, and settlement
- tracks reports and CSV exports
- supports manual reconciliation workflows
- applies budgets, spend policies, and accounting mappings
- records audit and transaction status history

## Current Stack

- Python 3.13
- Flask
- Flask-SQLAlchemy
- Flask-Migrate / Alembic
- Flask-WTF
- Flask-Limiter
- WTForms
- PostgreSQL via `psycopg`
- Jinja templates with server-rendered HTML

## Repository Layout

```text
vynfy_ledger/
app/                    Flask app package
  admin/                admin views
  auth/                 login, registration, and password reset
  dashboard/            dashboard aggregation and views
  models/               SQLAlchemy models
  reconciliation/       reconciliation flows
  reports/              reports and CSV export
  settings/             categories, accounts, users, budgets, policies, mappings
  setup/                first-run bootstrap, baseline seeding, balance maintenance
  static/               CSS and JS
  templates/            Jinja templates
  transactions/         revenue and expense flows
  utils/                auth, time, security, formatting, enums, types
migrations/             Alembic migration history
scripts/                operational scripts, including SQLite -> PostgreSQL import
tests/                  pytest suite
.env.example            environment template
requirements.txt        Python dependencies
run.py                  local app entrypoint
```

## Quick Start

This is the shortest path from empty repo checkout to usable local app.

### 1. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use the venv interpreter directly in all commands below:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

### 2. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Create `.env`

```powershell
Copy-Item .env.example .env
```

The app loads `.env` automatically through `python-dotenv`.

### 4. Set `DATABASE_URL`

Point the app at PostgreSQL.

Example:

```text
postgresql+psycopg://<user>:<password>@localhost:5432/vynfy_ledger
```

If your password contains reserved URL characters such as `#`, encode them in the URL.

### 5. Apply migrations

```powershell
python -m flask --app run.py db upgrade
```

### 6. Run the app

```powershell
python run.py
```

Default local URL:

```text
http://127.0.0.1:5000
```

### 7. Initialize the workspace

Fresh installs are not usable until the first admin and baseline setup data exist.

Open:

```text
http://127.0.0.1:5000/login
```

For local development, if the system has no admin yet, the login page shows an `Initialize system` link automatically.

For production, bootstrap is intentionally gated. Set both:

- `BOOTSTRAP_SETUP_ENABLED=true`
- `BOOTSTRAP_SETUP_TOKEN=<one-time-secret>`

Then open `/login` and use the `Initialize system` link. That first-run flow:

- creates the first admin
- seeds baseline categories
- seeds a baseline account
- seeds baseline payment methods

After the first admin is created, the bootstrap route disables itself automatically. In production, remove or rotate `BOOTSTRAP_SETUP_TOKEN` after bootstrap.

If you prefer not to use the browser bootstrap flow, you can create the first admin directly from the CLI:

```powershell
python -m flask --app run.py create-admin
```

## First-Time Onboarding Flow

If you are starting from an empty PostgreSQL database, use this order:

1. configure `.env`
2. run `flask db upgrade`
3. start the app
4. open `/login`
5. either run `flask create-admin` or, if using the browser bootstrap flow, confirm `BOOTSTRAP_SETUP_ENABLED=true` and `BOOTSTRAP_SETUP_TOKEN` are set in production
6. use `Initialize system` only if you chose the browser bootstrap flow
7. sign in as the first admin
8. review `/setup`
9. adjust accounts, categories, payment methods, users, budgets, and policies as needed

What “ready” means in this app:

- at least one active admin exists
- at least one active revenue category exists
- at least one active expense category exists
- at least one active account exists
- at least one active payment method exists

Until those exist, the app shows setup guidance and blocks simplified transaction entry instead of failing deep inside service code.

## Local Development Guide

### Recommended daily workflow

1. activate the virtual environment
2. confirm `.env` points to the intended Postgres database
3. run migrations
4. run the app
5. run tests before committing

### Development commands

Run the app:

```powershell
python run.py
```

Show current migration:

```powershell
python -m flask --app run.py db current
```

Show migration history:

```powershell
python -m flask --app run.py db history
```

Apply migrations:

```powershell
python -m flask --app run.py db upgrade
```

Generate a migration:

```powershell
python -m flask --app run.py db migrate -m "Describe the schema change"
```

## Environment Variables

Use `.env.example` as the starting point.

### Required in production

- `SECRET_KEY`
- `SECURITY_PASSWORD_SALT`
- `DATABASE_URL`

Production secrets must be unique and at least 32 characters long.

### Core settings

- `FLASK_APP`
- `FLASK_ENV`
- `APP_ENV`
- `DATABASE_URL`
- `COMPANY_NAME`

### Security and session settings

- `ACCESS_SESSION_MINUTES`
- `SESSION_ROTATE_AFTER_MINUTES`
- `LOGIN_LOCKOUT_BASE_MINUTES`
- `MAX_LOGIN_LOCKOUT_MINUTES`
- `MAX_FAILED_LOGINS`
- `PASSWORD_RESET_MINUTES`
- `ADMIN_STEP_UP_MINUTES`
- `WTF_CSRF_TIME_LIMIT`
- `FORCE_HTTPS`
- `TRUST_PROXY_COUNT`
- `REGISTRATION_ENABLED`
- `SELF_SERVICE_PASSWORD_RESET_ENABLED`
- `RATELIMIT_STORAGE_URI`

## Setup and Maintenance Commands

The app now includes first-admin, setup, and balance-maintenance CLI commands.

### Create an admin from the CLI

Creates an admin account directly without using the browser bootstrap flow.

```powershell
python -m flask --app run.py create-admin
```

Use this when:

- you want to create the first admin without opening `/setup/initialize`
- you are working in a shell-only environment
- you need a direct recovery path for internal environments

Admins created with this command are active immediately and have both revenue and expense creation permissions.

### Setup status

Shows whether the workspace is ready and which prerequisites are missing.

```powershell
python -m flask --app run.py setup status
```

### Seed baseline data

Creates baseline categories, account, and payment methods. The command is idempotent.

```powershell
python -m flask --app run.py setup baseline
```

Use this when:

- you want to seed setup data without using the browser
- you need to repair a partially configured local environment
- you want to make sure a fresh database has the minimum required records

### Check account balance drift

Compares cached account balances against balances recomputed from transactions.

```powershell
python -m flask --app run.py balances check
```

### Recalculate cached balances

Recomputes and stores the cached balance for every account.

```powershell
python -m flask --app run.py balances recalc
```

Use this after:

- imports
- manual data repair
- debugging ledger discrepancies
- adding new transaction workflows that may affect balances

## Application Setup Pages

### `/setup/initialize`

This route is the one-time first-admin bootstrap flow.

Behavior:

- available only when no active admin exists
- creates the first admin
- seeds baseline setup data
- redirects back to login after success
- becomes unavailable after successful bootstrap

### `/setup`

This page is the operational readiness checklist for a signed-in user.

For admins, it shows:

- which setup items are still missing
- links to the relevant settings pages
- a button to seed baseline setup data

For non-admin users, it explains that setup is incomplete and some actions are unavailable until an admin finishes configuration.

## Fresh Install Expectations

These behaviors are intentional:

- simplified revenue entry chooses the first active revenue category and first active account
- simplified expense entry chooses the first active expense category and first active account
- if setup is incomplete, those entry pages show guidance instead of hard-failing
- history shows better empty states:
  - no transactions yet
  - no records in the selected period
  - setup incomplete
  - current filters exclude all records

## Authentication Notes

Current auth behavior includes:

- password login
- optional self-registration when explicitly enabled
- self-service password reset only when explicitly enabled
- first-admin bootstrap for empty installs
- admin-created users are usable immediately
- session rotation
- admin route freshness checks

Notes:

- self-registration is not the same thing as first-admin bootstrap
- bootstrap is only for the very first admin on an empty system
- normal user creation after that happens through admin settings

## Transactions, History, and Setup Dependencies

Before operators can use simplified transaction entry reliably, the system needs:

- at least one active account
- at least one payment method
- at least one active revenue category for revenue entry
- at least one active expense category for expense entry

If you see disabled transaction entry or setup warnings, check `/setup` first.

## Database and Migrations

This project uses Flask-Migrate / Alembic.

Useful commands:

```powershell
python -m flask --app run.py db current
python -m flask --app run.py db history
python -m flask --app run.py db upgrade
python -m flask --app run.py db downgrade
python -m flask --app run.py db migrate -m "Describe the schema change"
```

Migration expectations:

- keep model changes and migration files in the same change set
- review autogenerated migrations before committing
- do not edit historical migrations casually
- prefer additive, explicit migrations for indexes and schema changes

## SQLite to PostgreSQL Migration Script

The repo includes a one-time importer:

```text
scripts/sqlite_to_postgres.py
```

Purpose:

- read from a legacy SQLite database
- write into a migrated PostgreSQL schema
- preserve specific users explicitly
- remove mock or unwanted rows during import
- support dry-run validation before writing

Example dry run:

```powershell
.\.venv\Scripts\python.exe scripts\sqlite_to_postgres.py ^
  --source instance\vynfy_ledger.db ^
  --target-url postgresql+psycopg://<user>:<password>@localhost:5432/vynfy_ledger ^
  --dry-run
```

Example real import:

```powershell
.\.venv\Scripts\python.exe scripts\sqlite_to_postgres.py ^
  --source instance\vynfy_ledger.db ^
  --target-url postgresql+psycopg://<user>:<password>@localhost:5432/vynfy_ledger
```

The importer expects the PostgreSQL schema to already exist via Alembic migrations.

Recommended import order:

1. create the target Postgres database
2. configure `DATABASE_URL`
3. run `flask db upgrade`
4. run the importer
5. sign in with the imported admin account
6. run `flask balances check`
7. review `/setup`

## Render Hosting Prep

The repo includes a Render blueprint:

```text
render.yaml
```

What it prepares:

- a Render PostgreSQL database named `vynfy-ledger-db`
- a Python web service named `vynfy-ledger`
- `DATABASE_URL` wired from the Render database connection string
- generated `SECRET_KEY` and `SECURITY_PASSWORD_SALT`
- `APP_ENV=production`
- self-service registration disabled by default
- self-service password reset disabled by default
- `gunicorn run:app` as the production start command

### Before creating resources

Review `render.yaml` and adjust names, region, or plan settings if needed.

### After the web service is created

Run migrations against the Render database:

```powershell
python -m flask --app run.py db upgrade
```

If you are using Render Shell or a Render job, make sure the environment includes the production `DATABASE_URL`.

### Empty production database onboarding

For a brand-new production database:

1. deploy the service
2. run `flask db upgrade`
3. either run `flask create-admin` or enable the bootstrap route and use `Initialize system`
4. sign in as the first admin
5. review `/setup`

### Importing legacy SQLite data into Render Postgres

The recommended sequence is:

1. create the Render Postgres database
2. deploy the web service
3. run `flask db upgrade` against Render Postgres
4. run `scripts/sqlite_to_postgres.py` against the Render database URL
5. verify the imported admin account and baseline data
6. run `flask balances check`

The importer should be run only after the target schema exists.

## Testing

Run the full suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```

Run targeted files:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_auth.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_setup.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_transactions.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_reports.py -q
```

Notes:

- the test suite uses its own test database configuration
- tests create isolated databases under `.tmp-tests`
- use the repo virtualenv explicitly if you see missing-package errors

## Filesystem Behavior

- uploads are stored in `instance/uploads`
- the app enforces a max request size of 5 MB

## Troubleshooting

### Missing Flask packages or import errors

Use the repo interpreter:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Tables are missing

Apply migrations:

```powershell
python -m flask --app run.py db upgrade
```

### The app starts but transaction entry is unavailable

Open `/setup` and confirm the following exist:

- one active revenue category
- one active expense category
- one active account
- one payment method

If needed, run:

```powershell
python -m flask --app run.py setup baseline
```

### Login page does not show `Initialize system`

Check these conditions:

- an active admin must not already exist
- in production, `BOOTSTRAP_SETUP_ENABLED` must be `true`
- in production, `BOOTSTRAP_SETUP_TOKEN` must be set

If this is a fresh environment and you expected bootstrap to be available, inspect the `users` table and confirm there is no active admin.

### Local app still shows old SQLite-era data

Check `.env` and confirm `DATABASE_URL` points to PostgreSQL, not an old database.

### Cached balances look wrong

Check:

```powershell
python -m flask --app run.py balances check
```

Repair:

```powershell
python -m flask --app run.py balances recalc
```

### HTTPS redirects break local development

Set:

```text
FORCE_HTTPS=false
TRUST_PROXY_COUNT=0
```

## Contribution Notes

- keep route handlers thin
- keep business rules in service modules
- add or update tests for behavior changes
- keep migrations in sync with schema changes
- avoid compatibility layers that are no longer used in production
- update `.env.example` and this README when setup changes
- preserve PostgreSQL via `psycopg` as the default driver unless there is a deliberate migration plan

## Security Notes

- do not commit real secrets, database URLs, or API keys
- production requires strong `SECRET_KEY` and `SECURITY_PASSWORD_SALT`
- cookies are secure in production
- CSRF is enabled outside testing
- audit logging exists for sensitive actions

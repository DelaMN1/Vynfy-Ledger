# Database Environment Notes

## Current Concern

Local development is currently mixed with a remote Render PostgreSQL database. That setup makes the app feel slower than it should and creates environment confusion during day-to-day work.

## Why This Matters

- Requests to the Render database add network round-trip latency.
- Local UI and backend changes can feel sluggish even when the code is fine.
- It becomes easier to accidentally test against shared or production-like data.
- Performance troubleshooting becomes misleading because local slowness is partly infrastructure-related.

## Recommended Approach

Use a fully local PostgreSQL database for normal development, and use the Render database only for staging or verification.

### Preferred Workflow

1. Local development:
   - local app
   - local PostgreSQL
2. Verification or staging checks:
   - local or deployed app
   - Render PostgreSQL only when needed
3. Production:
   - deployed app
   - production Render PostgreSQL

## Suggested Environment Strategy

### Best default

Use local Postgres as the default development database.

Why:

- removes remote latency from normal development
- makes app responsiveness more honest
- avoids accidental changes to shared data
- reduces dependence on network quality and Render uptime

### Good secondary option

Switch to Render only when you need to:

- reproduce a production-only issue
- test against production-like data volume
- validate migrations or reporting behavior before deploy

## Options Considered

### Option 1: Local Postgres by default, Render only when manually switched

This is the cleanest option.

- `.env` points to local Postgres for daily work
- Render connection is kept separately and used only when required

### Option 2: Local Postgres for writes, Render for occasional comparison

This can work if production-like data shape is useful during debugging.

- build and test features locally
- temporarily switch to Render for comparison or validation

### Option 3: Formal development, staging, and production separation

This is the long-term operational model.

- development = local app + local Postgres
- staging = deployed app + staging database
- production = deployed app + production database

## What To Avoid

- using the Render database as the default local development database
- treating one shared database as both dev and production-like infrastructure
- making performance judgments from a local app backed by a remote DB

## Practical Next Steps

1. Set up a local PostgreSQL database for regular development.
2. Keep the Render connection string separate from the normal local `.env`.
3. Use Render only for verification passes.
4. If needed later, create a simple environment-switching workflow for local vs. Render DB usage.

## Recommendation

The best immediate move is:

Use local PostgreSQL as the default development database, and treat Render as a staging or verification database only.


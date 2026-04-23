# Archived Two-Step Login Design

This project previously used an email-based second step after password entry.

## Removed Runtime Flow

The retired login flow worked like this:

1. User submitted email and password at `/login`.
2. Backend validated the password and email verification state.
3. A `LoginChallenge` record was created with:
   - hashed 6-digit code
   - expiry time
   - attempt counter
   - request IP and user agent
4. The user received:
   - a one-time numeric code by email
   - a magic-link URL that completed the same challenge
5. The app redirected the browser to `/login/verify`.
6. Successful code entry or magic-link use marked the challenge consumed and created the authenticated session.

## Retired Components

- Routes:
  - `/login/verify`
  - `/login/verify/resend`
  - `/login/magic/<token>`
- Forms:
  - `LoginCodeForm`
  - `ResendLoginCodeForm`
- Service responsibilities:
  - challenge creation
  - resend logic
  - magic-link completion
  - code verification
- Template:
  - `app/templates/auth/verify_login.html`

## Data Model Notes

The database still contains legacy artifacts from the old flow:

- `login_challenges` table
- `user_sessions.second_factor_verified_at`

The current app no longer uses `login_challenges`.

The `second_factor_verified_at` column is still present because it is reused as the timestamp of the user's last full password authentication. That keeps the admin re-auth freshness check working without forcing a destructive schema change.

## If You Want To Reintroduce Two-Step Later

You would need to restore all of the following:

1. Password-first login route that creates a challenge instead of a session.
2. Challenge verification route and resend route.
3. Email delivery for one-time login codes.
4. Optional magic-link completion route if you still want email link login.
5. Tests for:
   - challenge expiry
   - resend invalidation
   - code brute-force lockout
   - magic-link replay prevention
   - admin step-up freshness

## Why It Was Removed

The active codebase now uses a hardened password-only flow because the email-based second step was creating operational friction. The current security posture relies on:

- strong password policy
- aggressive failed-login lockout
- session rotation
- session revocation on fresh login
- session revocation on password reset
- CSRF protection
- secure response headers and CSP
- recent password-auth freshness for admin actions

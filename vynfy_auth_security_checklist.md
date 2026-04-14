# Vynfy Ledger — Authentication Security Audit Checklist for Codex

## Purpose
This document is a **strict audit checklist** Codex must run against the codebase to ensure authentication and security are production-ready.

Codex must:
- Review the entire codebase
- Identify violations
- Fix them
- Refactor where necessary
- Not skip any item

---

# 🔐 15 Critical Auth Mistakes (MUST FIX ALL)

## 1. JWT stored in localStorage ❌
- localStorage is vulnerable to XSS
- Any script can read tokens

### Required Fix:
- Store tokens in **httpOnly cookies**
- Cookies must be:
  - HttpOnly
  - Secure (production)
  - SameSite=Lax or Strict

---

## 2. Weak JWT secret ❌
- Common secrets like:
  - "secret"
  - "jwt_secret"
  - tutorial defaults

### Required Fix:
- Generate a **256-bit random secret**
- Store in environment variable
- Example:
openssl rand -hex 32

---

## 3. No refresh token rotation ❌
- Stolen refresh token remains valid forever

### Required Fix:
- Rotate refresh token on every use
- Invalidate previous token immediately
- Store refresh tokens server-side (DB)

---

## 4. No account lockout ❌
- Allows brute-force attacks

### Required Fix:
- Lock account after 10 failed attempts
- Implement exponential backoff
- Store:
  - failed_login_attempts
  - locked_until timestamp

---

## 5. Inconsistent auth middleware ❌
- Some routes protected, others open

### Required Fix:
- Audit EVERY route
- Apply authentication middleware globally
- Explicitly mark public routes

---

## 6. Different error messages ❌
- "User not found" vs "Wrong password"

### Required Fix:
Always return:
Invalid email or password

---

## 7. Password reset tokens never expire ❌

### Required Fix:
- Tokens must expire in:
  - 15 to 60 minutes max
- Use signed tokens with expiry

---

## 8. OAuth redirect not validated ❌

### Required Fix:
- Whitelist allowed redirect URIs
- No dynamic redirects

---

## 9. No email verification ❌

### Required Fix:
- User must verify email before access
- Block login until verified

---

## 10. Sessions not invalidated on logout ❌

### Required Fix:
- Delete session / revoke token server-side

---

## 11. Weak password storage ❌

### Required Fix:
- Use ONLY:
  - bcrypt
  - argon2
- Minimum 12 rounds

---

## 12. No HTTPS enforcement ❌

### Required Fix:
- Force HTTPS
- Redirect HTTP → HTTPS

---

## 13. Client-side role checks ❌

### Required Fix:
- ALL authorization must be server-side

---

## 14. No 2FA for admin ❌

### Required Fix:
- Add 2FA for admin routes
- Use TOTP or magic link

---

## 15. Test credentials in production ❌

### Required Fix:
- Remove all test users
- Audit database

---

# 🔍 Codex Execution Instructions

Codex must:

1. Scan entire codebase
2. Identify violations
3. Fix them
4. Add missing features
5. Add tests
6. Ensure no regressions

---

# 🚨 Final Requirement

The system is NOT production-ready unless:
- ALL 15 issues are resolved
- Security is enforced consistently

---

# 🎯 Goal

Ensure Vynfy Ledger has:
- secure authentication
- zero common vulnerabilities
- production-grade auth system

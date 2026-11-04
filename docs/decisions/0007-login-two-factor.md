# 0007 Login: password plus authenticator app, for every user

- Status: decided, 4 Nov 2026
- Context: design rule 16 puts users in each tenant's database. The roadmap asks for TOTP two-factor for admin and submit roles, but roles arrive in Phase 1.
- Decision:
  - Users are `accounts.User` (a custom user model, set before any real users exist) in the tenant database, with sessions also stored there. A login at one tenant's address cannot open another tenant, and the same username in two tenants means two unrelated people.
  - Logging in takes two steps: password, then a 6-digit authenticator-app code (RFC 6238). Until roles exist, **every** user must set up the app at first login; there is no password-only way in. When roles arrive we can relax this for view-only roles if wanted.
  - Five wrong passwords or codes lock the account for 15 minutes. A code is accepted only once. The step between password and code expires after 5 minutes.
  - Authenticator secrets are encrypted at rest with a key derived from `DJANGO_SECRET_KEY`. Rotating that key means everyone sets up the app again.
  - No public sign-up or "forgot password" email yet. An Owner runs `create_tenant_user` (with `--reset` for a lost password or phone), which prints a one-time link valid 24 hours. The token sits after `#` so it never reaches server logs.
- Later: recovery codes, password reset by email once outbound mail exists, per-role 2FA rules, admin screens for users.

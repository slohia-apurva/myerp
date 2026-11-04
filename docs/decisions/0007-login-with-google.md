# 0007 Sign in with Google; MyERP keeps no passwords

- Status: decided, 4 Nov 2026 (replaces a first draft with MyERP passwords plus an authenticator app)
- Context: Sidharth asked to avoid usernames and extra passwords, since most staff are already signed in to Google in their browser. The roadmap asks for two-factor login for anyone who can post. Users live in each tenant's database (design rule 16).
- Decision:
  - A person is known by **email address** (`accounts.User`, a custom user model). They sign in with **Google**: the browser shows Google's button, Google returns a signed ID token, and the server checks it (our client id, Google issuer, unexpired, verified email). MyERP stores no passwords.
  - Signing in only works if a tenant admin has **added that email** to the tenant. Sessions are stored in the tenant database, so a sign-in at one tenant's address never opens another.
  - At first sign-in we record Google's permanent account id (`sub`). If the email address is later moved to a different Google account, that account cannot sign in.
  - Two-step verification and leaver handling sit with Google. For apurva.org.in, turn on **enforced 2-Step Verification** in the Workspace admin console; suspending a leaver's Workspace account ends their MyERP access at the next sign-in. Deactivate them in MyERP too.
  - SMS OTP was rejected for sign-in (SIM-swap risk, DLT registration and per-message cost in India). An **email one-time code** fallback for people without a Google account comes in a later slice, together with outbound email.
- Consequences:
  - Google cannot use wildcard origins, so every address people sign in at must be listed on the OAuth client. Before SaaS launch, use one central sign-in address (e.g. `login.myerp.in`) that hands the session to the tenant's subdomain.
  - The OAuth consent screen is Internal (apurva.org.in only) for now; going External for other tenants needs Google's brand verification.
  - Roles and a Users screen for tenant admins come next; until then users are added with `manage.py create_tenant_user`.

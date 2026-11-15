# Backend step 2: Google registration and approval

Plan for the second piece of code: users, Google login, sessions and the approval of new users. Same method as step 1: one small pull request at a time towards `staging`, each with its tests and a short explanation of the non-obvious choices.

Status: plan, to be reviewed. Nothing here has been implemented yet.

## Goal

A person signs in with Google. A new account stays **pending** until an administrator approves it. The account whose verified email equals `ADMIN_EMAIL` is created as an active administrator. Administrators approve, disable, promote and demote users; the last active administrator cannot be removed.

The rules come from the README ("Access and administrator") and `CLAUDE.md` ("Security and data rules").

## Out of scope

The Angular login page (frontend step), Garmin keys and sync, Row-Level Security policies (they arrive with the first table of personal data, see "Row-Level Security" below), e-mail notifications to administrators, and access tokens for the MCP server.

## Decisions (proposed)

### Login flow: OAuth 2.0 authorization code with PKCE, run by the backend

1. The browser opens `GET /api/auth/google/login`. The backend redirects to Google with `state`, `nonce` and a PKCE challenge, kept in a short-lived signed cookie.
2. Google redirects back to `GET /api/auth/google/callback?code=...`. The backend checks `state`, exchanges the code (with `GOOGLE_CLIENT_SECRET` and the PKCE verifier) and validates the ID token: signature with Google's published keys, issuer, audience (`GOOGLE_CLIENT_ID`), expiry and `nonce`.
3. It requires `email_verified = true`, finds or creates the user, opens a session and redirects to the frontend.

Why on the backend: the client secret already listed in `.env.example` must never reach the browser, and the backend is the only place that can decide who the user is. PKCE and `state` protect the redirect from code interception and from login CSRF.

Library: **Authlib** (BSD-3-Clause) for the OpenID Connect client and ID token validation, rather than a hand-written flow: the details (key rotation, `nonce`, `state`) are easy to get wrong.

### Identity: Google's `sub`, not the email

A user is identified by Google's `sub` claim, which never changes. The email is stored (normalised to lowercase) and refreshed at each login, but it is not the key: a Google account can change address.

### Our own session: short access token, rotated refresh token

After the callback the backend issues its own tokens; Google's tokens are not kept.

- **Access token**: a JWT signed with `SECRET_KEY` (HS256, **PyJWT**, MIT), valid `ACCESS_TOKEN_MINUTES` (15). It carries only the user id and the token type; status and role are read from the database on every request, so a disabled or demoted user loses access within one request, not at expiry.
- **Refresh token**: a random opaque value, valid `REFRESH_TOKEN_DAYS` (30), stored only as a SHA-256 hash in a `refresh_tokens` table. Each use **rotates** it (the old one is revoked, a new one is issued). Reusing a revoked token is treated as theft and revokes the whole chain of that session.
- **Sliding refresh**: every rotation issues a token valid another `REFRESH_TOKEN_DAYS`, so a person who uses the site at least once a month stays signed in; after 30 days of inactivity they sign in with Google again.
- **Absolute lifetime**: a session (the chain of refresh tokens started by one Google login) ends after `SESSION_MAX_DAYS` (90, new setting) whatever the activity, and the person signs in with Google again. It bounds how long a stolen session can live and re-checks the Google account periodically.
- Logout revokes the refresh token and clears the cookies.

### Tokens in HttpOnly cookies

| Cookie | Name (staging, production) | Path | SameSite | Max age |
| --- | --- | --- | --- | --- |
| Access token | `__Host-sportlab_access` | `/` | `Strict` | `ACCESS_TOKEN_MINUTES` |
| Refresh token | `__Secure-sportlab_refresh` | `/api/auth` | `Strict` | `REFRESH_TOKEN_DAYS` |
| Login state (`state`, `nonce`, PKCE verifier, signed) | `__Host-sportlab_oauth` | `/` | `Lax` | 10 minutes |

- All cookies are `HttpOnly` (unreadable from JavaScript, so an injected script cannot steal them) and `Secure` (HTTPS only).
- The `__Host-` and `__Secure-` name prefixes make the browser enforce those rules: a `__Host-` cookie is accepted only over HTTPS, without a `Domain` attribute and for path `/`. Cookies are host-only, so staging and production sessions never mix even though both are under `lacrete.casa`.
- `Strict` for the session cookies: never sent from another site. The frontend is served from the same site as the API (`/api` behind the same reverse proxy, and the Angular development proxy locally), so this costs nothing and cookies work without CORS.
- `Lax` only for the login state cookie: the return from Google is a navigation from `accounts.google.com`, another site, and a `Strict` cookie would not be sent with it.
- In development (`ENVIRONMENT=development`, plain `http://localhost`): the same names without prefixes and without `Secure`, since there is no HTTPS.

CSRF: `SameSite=Strict` already keeps the session cookies off cross-site requests; as a second barrier, state-changing requests (`POST`/`PUT`/`PATCH`/`DELETE`) must carry a custom header (`X-Requested-With`), which a cross-site form cannot set. `GET` requests never change state.

### Account status and roles

- `status`: `pending` (new), `active` (approved), `disabled`.
- `role`: `user` or `admin`.
- Stored as text with a `CHECK` constraint rather than PostgreSQL `ENUM` types: adding a value to a `CHECK` is an ordinary migration, while enum changes are awkward to reverse.

A pending or disabled user can sign in and call `GET /api/auth/me` (so the interface can show "waiting for approval"); every other endpoint answers **403**.

### Administrator from `ADMIN_EMAIL`, only at creation

When a user is **created** and their verified email equals `ADMIN_EMAIL` (case-insensitive), the account is created with `role = admin` and `status = active`. Nothing happens at later logins: otherwise an administrator demoted by another administrator would become admin again just by signing in. The first registered user gets no special treatment.

If `ADMIN_EMAIL` is empty, nobody becomes administrator automatically; this is logged as a warning at startup outside development.

### The last administrator cannot be removed

Demoting or disabling an administrator is refused when they are the last **active** administrator. The check runs in the same transaction as the change, after locking the active administrators' rows (`SELECT ... FOR UPDATE`), so two administrators demoting each other at the same moment cannot leave the site with none.

### No personal data in logs

Logs carry the user id, never the email, the name or a token. Approvals record who approved and when (`approved_by`, `approved_at`).

### Row-Level Security

The `users` table is read by the authentication layer and by administrators, so it does not get per-user RLS policies. The RLS mechanism (setting the current user on each database session, policies on `user_id`) is introduced with the first table of personal data, where it can be tested against real cross-user reads.

## Pull requests

1. **Users table.** `app/models/user.py` (id UUID, `google_sub` unique, `email`, `display_name`, `status`, `role`, `created_at`, `last_login_at`, `approved_at`, `approved_by`), the first real Alembic revision, and tests: constraints (unique `sub`, allowed status and role values), and the existing migration tests (stairway, models match migrations) now cover a real table.
2. **Tokens.** `app/core/security.py` (create and verify access tokens; generate and hash refresh tokens), the `refresh_tokens` table and its migration, the `SESSION_MAX_DAYS` setting, and a check that `SECRET_KEY` is at least 32 characters in every environment (the `CHANGE_ME` placeholder is refused, and shorter HMAC keys are weak). Tests: expiry, wrong signature, wrong token type, rotation, reuse revokes the chain.
3. **Google login.** `GET /api/auth/google/login` and `GET /api/auth/google/callback`, user creation, the `ADMIN_EMAIL` rule, cookies. Tests use a **fake Google**: a local RSA key signs synthetic ID tokens, and the token exchange is replaced through a FastAPI dependency, so no test calls Google. Cases: new user is pending, `ADMIN_EMAIL` user is active admin, existing user keeps status and role, unverified email refused, wrong `state` or `nonce` refused.
4. **Session endpoints.** `GET /api/auth/me`, `POST /api/auth/refresh`, `POST /api/auth/logout`, and the dependencies `current_user`, `active_user`, `admin_user` that every later endpoint uses. Tests: missing or expired token gives 401, pending and disabled users get 403 outside `/me`, refresh rotation through the API, CSRF header required.
5. **User administration.** `GET /api/admin/users` (optional status filter), `POST /api/admin/users/{id}/approve`, `.../disable`, `.../role`. Tests: only admins, last-admin guard (including two concurrent demotions), approval records `approved_by`.
6. **Documentation and Bruno.** `docs/google-oauth.md` (creating the OAuth client in Google Cloud, redirect URIs for development, staging and production), the auth and admin requests in the Bruno collection (the sync test requires them from PR 3 on, so each PR adds its own), `backend/README.md` and `CLAUDE.md`.

## Choices to explain while implementing

- Why the session uses our tokens instead of Google's, and why the access token is short and the refresh token rotated.
- Why cookies instead of `localStorage`, and how `SameSite` plus a custom header stops CSRF.
- Why `sub` and not the email identifies a user.
- How the last-admin rule stays true under concurrent requests (row locks).
- How the fake Google in the tests works, and why tests never call the real one.

## Tests

- All synthetic: fake Google accounts with generated `sub` values and `example.com` addresses; no real account, name or email anywhere.
- Database tests on the development Compose locally and on the PostGIS service in CI, with the two roles (the application role must be enough for every auth operation).
- Ruff and pytest as in step 1.

## Definition of done for step 2

- A new Google account signs in and is pending; an admin approves it; it can then use the API.
- The `ADMIN_EMAIL` account is created as an active admin; the last admin cannot be demoted or disabled.
- Tokens are only in HttpOnly cookies, rotated on refresh, revoked on logout; reuse of a refresh token revokes the session.
- No email, name or token in the logs.
- `ruff check`, `ruff format --check` and `pytest` pass locally and in CI; the Bruno collection covers the new endpoints.

## Environments and redirect URIs

| Environment | Site | Google redirect URI |
| --- | --- | --- |
| Development | `http://localhost:8000` (backend; later the Angular proxy) | `http://localhost:8000/api/auth/google/callback` |
| Staging | `https://sportlab-staging.lacrete.casa` | `https://sportlab-staging.lacrete.casa/api/auth/google/callback` |
| Production | `https://sportlab.lacrete.casa` | `https://sportlab.lacrete.casa/api/auth/google/callback` |

Cookies are host-only (no `Domain` attribute), so a staging session is never sent to production or the other way round, even though both are under `lacrete.casa`.

## Open points

- **Google Cloud project**: the OAuth clients ("Web application", one per environment) are created by Paolo following [google-oauth.md](google-oauth.md). Until then the login is covered only by the automated tests with the fake Google.
- **Session settings**: confirmed by Paolo (15-minute access token, 30-day sliding refresh token, 90-day absolute lifetime, the cookie settings above).

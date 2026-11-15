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
- Logout revokes the refresh token and clears the cookies.

### Tokens in HttpOnly cookies

Both tokens travel in cookies with `HttpOnly` (unreadable from JavaScript, so an injected script cannot steal them), `Secure` (HTTPS only, except in development), `SameSite=Lax`, and a narrow path for the refresh cookie (`/api/auth`). The frontend is served from the same site as the API (`/api` behind the same reverse proxy, and the Angular development proxy locally), so cookies work without CORS.

CSRF: `SameSite=Lax` blocks cross-site `POST`/`PUT`/`PATCH`/`DELETE` with cookies; in addition, state-changing requests must carry a custom header (`X-Requested-With`), which a cross-site form cannot set. `GET` requests never change state.

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
2. **Tokens.** `app/core/security.py` (create and verify access tokens; generate and hash refresh tokens), the `refresh_tokens` table and its migration, settings check that `SECRET_KEY` is at least 32 characters outside development. Tests: expiry, wrong signature, wrong token type, rotation, reuse revokes the chain.
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

## Open points

- **Google Cloud project**: an OAuth client ("Web application") must be created by Paolo in Google Cloud Console before PR 3 can be tried in a browser; PR 3 and its tests do not need it. Redirect URIs: `http://localhost:8000/api/auth/google/callback` for development, and the staging and production URLs once their domains are fixed.
- **Staging domain**: production is `sportlab.lacrete.casa`; the staging address is needed for its redirect URI and cookie settings.
- **Requirements document**: the project document maintained outside the repository may already specify session lifetimes or flows; any difference with this plan should be settled before PR 2.

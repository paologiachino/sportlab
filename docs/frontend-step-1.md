# Frontend step 1: sign-in, approval and administration

Plan for the first frontend code: the Angular project, the session handling on top of the step 2 backend, and the pages that make sign-in and user approval usable from a browser. Same method as the backend steps: one small pull request at a time towards `staging`, each with its tests and a short explanation of the non-obvious choices.

Status: plan approved by Paolo. Nothing here has been implemented yet.

## Goal

A person opens the site, signs in with Google and lands on a page that matches their account: a home page if they are active, a "waiting for approval" page if they are pending, a "disabled" page if they are disabled. An administrator sees the list of users and approves, disables, promotes and demotes them without Bruno or copied cookies. The session renews itself silently while the site is in use, in one tab or many.

## Out of scope

Dashboards, activities, maps and every page with sports data (they need the Garmin sync); the profile and settings page; the production container that serves the built frontend and the routing in Traefik (deploy step); end-to-end browser tests (they need a running backend with a fake Google, better added with the deploy step); translations.

## Decisions (proposed)

### Angular project: standalone components, signals, no zone.js

- Created with the Angular CLI in `frontend/`, on the current stable Angular major (checked when the project is created). Angular releases a major every six months and supports each one for 18 months, so updates are routine `ng update` pull requests, not rewrites.
- **Standalone components** (no `NgModule`): every component declares what it imports. It is the default of current Angular and the one that the official documentation uses.
- **Signals** for state (the signed-in user, the user list): a signal is a value that the template re-reads automatically when it changes. Simpler than RxJS for state; RxJS stays where Angular uses it anyway (`HttpClient`).
- **Zoneless change detection**: Angular updates the page when a signal changes, instead of patching every browser event through `zone.js`. Default in new projects, less magic to explain.
- Strict TypeScript and strict templates (CLI default).

### Folder structure

```
frontend/src/app/
  core/       session, API access, interceptors, guards: one instance for the whole app
  features/
    auth/     login, pending, disabled pages
    home/     the page after sign-in (placeholder until there is data)
    admin/    user administration
  shared/     small reusable components (buttons, status badge)
```

Feature folders are lazy-loaded routes: the administration code is downloaded only by those who open it.

### Styling and tooling

- **Tailwind CSS** through the PostCSS setup the Angular CLI supports. No component library for now: the pages are few and simple, and a library is a large dependency to choose later, when the dashboards show what is needed.
- **ESLint** with `angular-eslint`, **Prettier** for formatting (as `CLAUDE.md` asks); `npm run lint` and `npm run format:check` run in CI.
- **Unit tests with Vitest**, the test runner of current Angular CLI projects, with `HttpTestingController` to fake the backend. No test calls the real backend or Google.
- Node.js version pinned in `frontend/.nvmrc` and used by CI (today CI says 22): the version is the active LTS that the chosen Angular supports, verified when the project is created.

### Same site as the API: the Angular development proxy

The step 2 cookies are `SameSite=Strict` and host-only, and the backend redirects to `/` after the Google callback. So the browser must see the frontend and the API on the **same address**:

- **Development**: `ng serve` on `http://localhost:4200` forwards `/api/...` to the backend on `http://localhost:8000` (`proxy.conf.json`). `PUBLIC_URL` becomes `http://localhost:4200`, so Google sends the browser back to the Angular server, which forwards the callback to the backend; the redirect to `/` then lands on the Angular app.
- The development Google client gets one more authorised redirect URI: `http://localhost:4200/api/auth/google/callback` (the `:8000` one can stay for using the backend alone).
- **Staging and production**: the reverse proxy serves the built frontend and `/api` on the same host (deploy step). No CORS anywhere.

### API access: one place, credentials and CSRF header

- Every request goes to a relative `/api/...` URL; the browser sends the cookies by itself (same origin). The frontend never reads or stores a token: they are `HttpOnly` cookies, invisible to JavaScript by design.
- An **HTTP interceptor** adds `X-Requested-With: XMLHttpRequest` to every `POST`/`PUT`/`PATCH`/`DELETE`, the CSRF header the backend requires.
- Sign-in is a **full page navigation** to `/api/auth/google/login`, not an `HttpClient` call: the browser has to follow the redirects to Google and back.

### Session: who is signed in

- A `SessionService` holds the current user (`GET /api/auth/me`) in a signal: `null` when signed out, otherwise id, email, name, status and role.
- It is loaded once when the app starts (an app initializer), so the guards below know the answer before the first page is drawn.
- Logout calls `POST /api/auth/logout`, clears the signal and goes to the login page.

### Silent refresh, once at a time across tabs

The access token lives 15 minutes. When a request gets **401**, an interceptor calls `POST /api/auth/refresh` and repeats the request once; if the refresh also fails, the session is over and the app goes to the login page.

The difficulty: the refresh token is **rotated**, and presenting an old one is treated as theft (step 2). If two requests, or two tabs, refresh at the same moment, the second one presents a token the first already replaced, and the backend ends the session. So:

- **Inside a tab**: concurrent 401s share one refresh in progress (the first starts it, the others wait for its result).
- **Across tabs**: the refresh runs inside a **Web Lock** (`navigator.locks.request('sportlab-refresh', ...)`, a browser API that gives a named lock to one tab at a time). Each successful refresh writes its time in `localStorage`; a request that got 401 and then obtains the lock checks it first: if a refresh happened after the request was sent, in this tab or another one, the cookies (shared by every tab) are already new, and the request is only repeated. The same check also merges the concurrent 401s of one tab, so a single mechanism covers both cases.
- `/api/auth/refresh`, `/api/auth/logout` and the Google redirects never trigger a refresh (no loops, nothing to keep). `/api/auth/me` does: after a pause longer than the access token's 15 minutes, its 401 only means that the access token expired, while the refresh token may still be valid.

Tests cover: one refresh for many concurrent 401s, retry after refresh, sign-out after a failed refresh, no refresh for the auth endpoints. The cross-tab case is tested with a fake lock in unit tests, and by hand with two tabs.

### Pages and route guards

| Route | Who | What |
| --- | --- | --- |
| `/login` | signed out | "Sign in with Google" button; shows a message if the sign-in failed |
| `/pending` | pending | "Your account is waiting for approval", logout |
| `/disabled` | disabled | "Your account is disabled", logout |
| `/` | active | placeholder home page with the user's name and logout |
| `/admin/users` | active admin | user list with status filter; approve, disable, change role |

**Guards** are functions that run before a route opens and redirect elsewhere: signed out → `/login`, pending → `/pending`, disabled → `/disabled`, non-admin on `/admin` → `/`. They are a convenience for the interface only: the backend checks every request anyway (401/403), so a modified frontend gains nothing.

The administration page shows the backend's refusals, never hides them: the last-admin guard and the other `409`/`404`/`403` answers become a message in Italian (the backend's `detail` is English, for developers), with a generic message for anything unexpected. Destructive actions (disable, demote) ask for confirmation. When administrators change their own role or status, the session is reloaded and the guards decide where they can stay.

### Failed sign-in: a small backend change

Today a failed callback (refused by Google, unverified email, Google unreachable) answers with a JSON error, which the browser shows as raw text. The callback will instead **redirect to `/login?error=<code>`** with a short code (`failed`, `unverified_email`, `unavailable`), and the login page shows a readable message. The code reveals nothing that the JSON did not already say. Backend tests are updated accordingly.

### Interface language

Decided: Italian text in the templates for now, without a translation framework, since Paolo and family use Italian. When the site becomes public, Angular's built-in i18n (`$localize`) marks the texts and adds English. Code, identifiers and comments stay in English as everywhere else.

## Pull requests

1. **Angular project.** `ng new` in `frontend/` (standalone, zoneless, strict), Tailwind, ESLint, Prettier, Vitest, `proxy.conf.json`, `.nvmrc`, `npm` scripts used by CI (`lint`, `format:check`, `test`, `build`), CI aligned to the Node version, `frontend/README.md` with the commands. One placeholder page and its test.
2. **API access and session.** CSRF interceptor, `SessionService` with `/me` at startup, logout, the refresh interceptor with the in-tab and cross-tab lock. Unit tests with `HttpTestingController`.
3. **Sign-in pages and guards.** `/login`, `/pending`, `/disabled`, the home placeholder, the guards, a minimal layout (header with name and logout). Includes the backend change for `/login?error=...`, with its tests.
4. **User administration page.** `/admin/users` with the status filter and the approve, disable and role actions, confirmation for destructive actions, error messages from the backend. Tests against a faked API.
5. **Documentation.** `PUBLIC_URL` and the new redirect URI in `.env.example`, `docs/google-oauth.md` and `backend/README.md`; `frontend/README.md`, the main README status and `CLAUDE.md` commands.

## Choices to explain while implementing

- Standalone components, signals and zoneless change detection, compared with the older `NgModule` and `zone.js` style found in many tutorials.
- How the development proxy makes the browser see one site, and why that keeps `SameSite=Strict` cookies working without CORS.
- What an interceptor is, and how the refresh interceptor avoids both loops and concurrent refreshes (in a tab and across tabs).
- Why the guards are only user experience and security stays in the backend.
- How `HttpTestingController` replaces the backend in tests.

## Tests

- Unit tests (Vitest) for the interceptors, the session service, the guards and the pages; all API answers faked, all users synthetic (`example.com` addresses).
- Backend: the updated callback tests, with the fake Google as in step 2.
- `npm run lint`, `npm run format:check`, `npm test` and `npm run build` locally and in CI; Ruff and pytest for the backend change.
- By hand in development: real Google sign-in through `localhost:4200`, two tabs open across an access token expiry.

## Definition of done for step 1

- From `http://localhost:4200` a new Google account signs in and sees the pending page; the admin approves it from `/admin/users`; after a reload the account sees the home page.
- The session survives an access token expiry without visible effects, with two tabs open, and without being ended by the reuse detection.
- A failed sign-in shows a readable message on the login page.
- Lint, format check, tests and build pass locally and in CI.

## Open points

- **Angular and Node versions**: fixed when the project is created (PR 1), after checking the current releases and their support windows.

Resolved: the interface is in Italian (see above); the development Google client already has the `http://localhost:4200/api/auth/google/callback` redirect URI.

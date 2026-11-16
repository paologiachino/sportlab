# Staging deploy: images, homelab and first release

Plan for the first deploy of Sportlab: Docker images built by GitHub Actions, stored in GHCR, and started on the homelab as the staging environment at `https://sportlab-staging.lacrete.casa`. The work is split between this repository (images) and [sportlab-infra](https://github.com/paologiachino/sportlab-infra) (environment, deploy workflow, procedures). Same method as the other steps: one small pull request at a time, each with a short explanation of the non-obvious choices.

Status: plan, to be reviewed. Nothing here has been implemented yet.

## Goal

A merge into `staging` produces two images tagged with the commit. A deploy started from GitHub runs, on the homelab, the migrations and then the new backend and frontend. From the home network or the VPN, `https://sportlab-staging.lacrete.casa` shows the login page; a Google sign-in with the staging client works, and an administrator approves a second account from the administration page. Going back to the previous version is one deploy with the previous tag.

## Out of scope

Production (a separate step, once staging has run for a while: it adds backups before migrations and possibly public access through Cloudflare Tunnel); the automatic deploy after every merge (see "Open points"); Garmin sync; monitoring and alerts; a Content Security Policy (to be added once the pages stabilise).

## What already exists

- `sportlab-infra`: draft (untested) `environments/staging/compose.yml`, `.env.example` and a manual `deploy-staging.yml` workflow for a self-hosted runner labelled `homelab`; the procedures in `docs/`.
- The dedicated database container `sportlab-postgres` (PostGIS 17-3.7) runs on the homelab, on the `sportlab-db` Docker network. The `sportlab_staging` database and its two roles are created; their password check is still to do (`sportlab-infra/docs/database.md`).
- The homelab's Traefik: wildcard certificate for `*.lacrete.casa`, `proxy` Docker network, `lan-only` middleware (LAN, Docker networks, Tailscale). AdGuard answers `*.lacrete.casa` with the server's local address, so the new name needs no DNS change.
- Not yet there: the runner, any image, a staging Google client.

## Decisions (proposed)

### Two images, built from this repository

**Backend** (`ghcr.io/paologiachino/sportlab-backend`):

- Multi-stage build on `python:3.12-slim`: a first stage installs the locked dependencies with `uv sync --locked --no-dev` into a virtual environment, the final stage copies only that environment and the application code. No compiler, no `uv`, no test tools in the final image.
- Runs as an unprivileged user, `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- The same image runs the migrations: the deploy starts it once with the command `alembic upgrade head`.
- A Docker health check on `/api/health`, written in Python (the slim image has no `curl`).

**Frontend** (`ghcr.io/paologiachino/sportlab-frontend`):

- Build stage on `node:26-alpine` (`npm ci`, `npm run build`); final stage `nginxinc/nginx-unprivileged` (BSD-2-Clause, runs as a normal user on port 8080) serving `dist/sportlab/browser`.
- An `nginx.conf` with the single-page-app fallback (every unknown path returns `index.html`, so a reload on `/admin/users` works), long caching for the hashed files and no caching for `index.html` (a new release is picked up at the next reload).
- nginx does not proxy `/api`: Traefik sends `/api` to the backend directly (below), so the frontend container knows nothing about the backend.

Base images are pinned to a version tag, and Dependabot (Docker ecosystem, added now that Dockerfiles exist) proposes updates.

### Built after the checks, tagged with the commit

- A new `images` job in `ci.yml`, after the backend, frontend and secret-scan jobs: on pull requests it **builds** both images without pushing (a broken Dockerfile fails the pull request); on pushes to `staging` and `main` it builds and **pushes** them.
- Tag: the full commit SHA, the only tag. No `latest` or `staging` tags: a moving tag would make "what is running" ambiguous, and `sportlab-infra` requires explicit tags.
- Pushing uses the workflow's own `GITHUB_TOKEN` with `packages: write`: no personal token. The packages stay private.

### Routing on the homelab: one host, two routers

| Router | Rule | Service |
| --- | --- | --- |
| `sportlab-staging-api` | ``Host(`sportlab-staging.lacrete.casa`) && PathPrefix(`/api`)`` | backend, port 8000 |
| `sportlab-staging-web` | ``Host(`sportlab-staging.lacrete.casa`)`` | frontend, port 8080 |

- Traefik gives priority to the longer rule, so `/api/...` reaches the backend and everything else the frontend. The browser sees one site, as with the Angular development proxy: the `SameSite=Strict` cookies work and there is no CORS.
- Both routers use `websecure` only and the **`lan-only`** middleware: staging is reachable from home and from the VPN, never from the Internet (no `public` entrypoint). Google sign-in still works, because the return from Google is a redirect in the person's browser, not a call from Google to the server.
- FastAPI's `/docs` and `/openapi.json` are outside `/api`, so they are not published.

### Containers and networks

| Service | Networks | Notes |
| --- | --- | --- |
| `migrate` | `sportlab-db` | runs `alembic upgrade head` and exits; gets only `DATABASE_MIGRATION_URL` |
| `backend` | `proxy`, `sportlab-db` | starts only after `migrate` succeeded; gets the application settings, not the migration role |
| `frontend` | `proxy` | static files only, no secrets |

Each container gets only the variables it needs, from two files on the homelab outside every repository: `/opt/sportlab/staging/backend.env` and `/opt/sportlab/staging/migrate.env` (examples in `sportlab-infra`).

### A small backend change: the application no longer needs the migration role

Today `Settings` (the application) inherits from `MigrationSettings`, so the backend refuses to start without `DATABASE_MIGRATION_URL`: the running application would have to hold the password of the role that can change the schema. The two settings classes are separated, so the backend container receives only the application role, as the least-privilege rule intends. Tests cover both: the application starts without the migration URL, Alembic still requires it.

### Deploy: started by hand from GitHub, run by the runner on the homelab

- A **self-hosted GitHub runner** on the homelab, registered only on the private `sportlab-infra` repository with the `homelab` label, installed as a service under a dedicated user. It connects outwards to GitHub: no port is opened.
- The workflow `deploy-staging.yml` (manual, `workflow_dispatch` with the commit SHA as input):
  1. logs in to GHCR with its own `GITHUB_TOKEN` (`packages: read`); the two packages grant read access to `sportlab-infra` in their settings, so no long-lived token is stored on the homelab;
  2. `docker compose pull`, then `up -d`: `migrate` runs first, then `backend` and `frontend` are replaced;
  3. waits for the backend health check and calls `https://sportlab-staging.lacrete.casa/api/health/db`;
  4. records the deployed SHA in `/opt/sportlab/staging/deployed-tag`, so the previous one is known for a rollback.
- **Rollback**: the same workflow with the previous SHA. Migrations are compatible with the previous code (project rule), so the older backend runs on the newer schema.
- Honest limit: a user that can run Docker is, in practice, root on the host. The protection is that only workflows from the private `sportlab-infra` repository, which only Paolo changes, run on this runner. The `staging` Environment of `sportlab-infra` is restricted to its `main` branch.

### Staging settings

- `ENVIRONMENT=staging`, `PUBLIC_URL=https://sportlab-staging.lacrete.casa`: secure cookies with the `__Host-`/`__Secure-` prefixes, https required at startup.
- Its own `SECRET_KEY` and `ENCRYPTION_KEY` (generated on the homelab, never reused from development).
- Its own Google client, **sportlab staging**, with the redirect URI `https://sportlab-staging.lacrete.casa/api/auth/google/callback` ([google-oauth.md](google-oauth.md)).
- `ADMIN_EMAIL`: the administrator account, as in development.
- Synthetic data only: no Garmin keys in staging.

## Pull requests

In this repository:

1. **Settings split.** `Settings` stops inheriting the migration URL; tests for both classes; `.env.example` comments.
2. **Backend image.** `backend/Dockerfile`, `backend/.dockerignore`; the CI `images` job builds it on pull requests. Checked locally: the image starts against the development database, `/api/health/db` answers, `alembic upgrade head` runs from it.
3. **Frontend image.** `frontend/Dockerfile`, `frontend/nginx.conf`, `frontend/.dockerignore`; built in CI. Checked locally: reload on a deep link, cache headers.
4. **Publishing.** The `images` job pushes both images to GHCR on pushes to `staging` and `main`; Dependabot for Docker; `docs/branch-and-deploy.md` updated.

In `sportlab-infra`:

5. **Staging environment.** `environments/staging/compose.yml` rewritten (networks, Traefik labels, health checks, the two env files), `.env.example` files split into `backend.env.example` and `migrate.env.example`, and the deploy workflow with the GHCR login, health check and recorded tag. Still marked as draft until step 6.
6. **Runner and first deploy.** The runner installation procedure in `docs/runner-homelab.md`, the first-deploy runbook (env files, package access, Google client, deploy, verification, rollback test) in `docs/deploy-and-rollback.md`; drafts marked as verified only after the real run.

## Steps for Paolo on the homelab and on GitHub

Done by hand, with the instructions in PR 6, because they need the server or the owner's accounts:

1. Install and register the runner (dedicated user, service, `homelab` label).
2. Finish the staging database checks in `sportlab-infra/docs/database.md` (passwords of the two staging roles).
3. Create `/opt/sportlab/staging/backend.env` and `migrate.env` from the examples, with new secrets.
4. In the GHCR package settings of `sportlab-backend` and `sportlab-frontend` (they appear after the first push), give `sportlab-infra` read access.
5. Create the Google client **sportlab staging** with its redirect URI, and add the accounts to the test users if the consent screen is still in Testing.

## Definition of done

- A merge into `staging` publishes `sportlab-backend:<sha>` and `sportlab-frontend:<sha>` to GHCR, only when the checks pass.
- The manual deploy with that SHA runs the migrations, then starts backend and frontend; `/api/health/db` answers `ok` through Traefik.
- From the LAN or the VPN: sign-in with Google, the administrator approves a second account, the session survives the access token expiry. From outside (mobile data, no VPN) the site is refused.
- A deploy with the previous SHA works (rollback tested once).
- The runner comes back after a homelab reboot.
- No secret in either repository, in the images or in the workflow logs.

## Open points

- **Automatic staging deploy after each merge.** Proposed for later: once the manual deploy is proven, the `images` job could notify `sportlab-infra` (`repository_dispatch`), which needs a fine-grained token stored in this repository and limited to `sportlab-infra`. Manual deploys until then.
- **Staging Google client**: to be created by Paolo (step 5), unless the development client should be reused (not recommended: separate clients keep the secrets separate).
- **Runner user and Docker access**: a dedicated user in the `docker` group is the simple option (see the honest limit above); rootless Docker would isolate more but changes how the homelab runs containers. Proposed: the simple option, documented.

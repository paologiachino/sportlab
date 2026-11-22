# CLAUDE.md — sportlab

Working rules for Claude Code in this repository. The owner is Paolo, who validates every change and also uses the project to learn: explain non-obvious choices and proceed in small steps.

## Project

Multi-user site for sports activities and health data downloaded from Garmin (Personal API), with a backend, frontend, MCP server and PostgreSQL database. Current phase: backend step 2 (Google sign-in, sessions, user approval, see `docs/backend-step-2.md`) and frontend step 1 (Angular sign-in, waiting pages, user administration, see `docs/frontend-step-1.md`) done. Next, in this order: the staging deploy on the homelab, then the Garmin keys and sync (backend step 3). Full description in `README.md` and in `docs/`.

**Migration to Zonedose (in progress):** the project is being renamed Zonedose and its backend moved to Orchard Core in the [zonedose](https://github.com/paologiachino/zonedose) repository (`docs/orchard-migration-plan.md` there). From phase 4 the Angular frontend here talks to that backend (`frontend/proxy.conf.json` points to `http://localhost:8080`); the FastAPI backend in `backend/` is paused and receives no new features.

## Stack (confirmed)

- Backend: Python, FastAPI, SQLAlchemy, Alembic.
- Database: PostgreSQL with PostGIS, in a dedicated container on the homelab (see `docs/postgis.md`).
- Frontend: Angular, TypeScript, Tailwind CSS.
- Maps: MapLibre GL, contour lines from a DEM.
- MCP: read-only server at first, on top of the same backend APIs.

## Working method

1. Always work on a branch (`feature/...`, `fix/...`, `chore/...`), never directly on `main` or `staging`.
2. Small steps: one function or module at a time, with tests, then a pull request.
3. Briefly explain every non-obvious choice (Angular structure, use of SQLAlchemy, sync logic) so Paolo can validate it and learn.
4. Do not call a piece of work finished without running tests and style checks. If you cannot run them, say so.
5. One pull request at a time, described in English, with what changes and how to test it.

## Conventions

- Chat with Paolo is in Italian. Code, identifiers, workflows, comments, documentation, commit messages and pull request descriptions are in English.
- Commit messages in English with a prefix: `feat:`, `fix:`, `chore:`, `docs:`, `test:`.
- Python: formatting and linting with Ruff, types where useful. TypeScript: ESLint and Prettier.

## Security and data rules

- No secrets in the code or in the repositories: everything comes from environment variables (see `.env.example`).
- Every piece of personal data has a `user_id`; every query goes through the layer that filters by the authenticated user. The database adds Row-Level Security as a second barrier.
- Users register with Google and stay "pending" until the administrator approves them.
- The administrator is impersonal: no name or email in the code or in the seeding. The `admin` role goes to the email in `ADMIN_EMAIL` at first login; open registration never assigns roles.
- Users' Garmin keys are stored encrypted; they are never written to logs.
- Migrations use Alembic and are written to be compatible with the previous version of the code.
- Test data is synthetic only; never real health data in development or staging.

## Commands

Details and explanations in `backend/README.md`.

```sh
cp .env.example .env                       # once; replace every CHANGE_ME
docker compose up -d --wait                # development PostGIS (repository root)

cd backend
uv sync                                    # dependencies (Python 3.12 from .python-version)
uv run alembic upgrade head                # migrations
uv run uvicorn app.main:app --reload       # backend on http://127.0.0.1:8000

uv run ruff check                          # style checks, required before a pull request
uv run ruff format --check
uv run pytest                              # tests; database tests need the Compose database

cd ../bruno && bru run --env Local         # Bruno collection against the running backend

cd ../frontend                             # details in frontend/README.md
npm ci                                     # dependencies (Node.js from .nvmrc)
npm start                                  # http://localhost:4200, /api forwarded to the backend
# Google sign-in: OAuth client per docs/google-oauth.md, PUBLIC_URL=http://localhost:4200, open http://localhost:4200
npm run lint && npm run format:check       # style checks, required before a pull request
npm test -- --watch=false                  # unit tests (Vitest), never call the backend
npm run build
```

Shell variables take precedence over `.env`. Database tests are skipped locally without a database but must run in CI. Tests never call Google: they use the fake Google in `backend/tests/fake_google.py`.

## Licence

AGPL-3.0. New dependencies must have compatible licences.

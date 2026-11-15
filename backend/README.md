# Backend

REST API, database models, Garmin sync and migrations. Python with FastAPI, SQLAlchemy and Alembic.

Status: step 2 done (Google sign-in, sessions, user approval and roles), on top of step 1 (health endpoints, settings, database session, Alembic). Plans: `docs/backend-step-1.md`, `docs/backend-step-2.md`.

## Development

Requirements: [uv](https://docs.astral.sh/uv/) and Docker Desktop. uv installs Python 3.12 by itself (see `.python-version`).

```sh
# 1. Configuration, once: copy the example and replace every CHANGE_ME
#    (local values only, letters and digits)
cp .env.example .env

# 2. Development database (PostGIS), from the repository root
docker compose up -d --wait

# 3. Backend, from backend/
cd backend
uv sync                                  # create .venv and install dependencies
uv run alembic upgrade head              # apply the migrations
uv run uvicorn app.main:app --reload     # http://127.0.0.1:8000/api/health
```

Interactive API docs: http://127.0.0.1:8000/docs. A Bruno collection is in `bruno/` (see `bruno/README.md`).

Variables set in the shell take precedence over `.env`: after an `export DATABASE_URL=...`, open a new terminal or `unset` it.

### Google sign-in

Without `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` the backend starts normally and `/api/auth/google/login` answers `503`; the tests never need them (they use a fake Google). To sign in for real, create the OAuth client following `docs/google-oauth.md`, fill in `.env` (with `ADMIN_EMAIL` for the first administrator), restart the backend and open http://localhost:8000/api/auth/google/login, using `localhost` rather than `127.0.0.1` so the browser keeps the login cookie.

| Endpoint | Who | What |
| --- | --- | --- |
| `GET /api/auth/google/login` | anyone | redirect to Google |
| `GET /api/auth/me` | signed in (also pending or disabled) | the current user |
| `POST /api/auth/refresh` | holder of the refresh cookie | new access and refresh cookies |
| `POST /api/auth/logout` | anyone | end the session, clear the cookies |
| `GET /api/admin/users`, `POST /api/admin/users/{id}/approve`, `.../disable`, `.../role` | active admins | user administration |

The session is held in HttpOnly cookies; `POST`, `PUT`, `PATCH` and `DELETE` requests under `/api/` must carry the `X-Requested-With` header (CSRF barrier), otherwise `403`. New users are `pending` and get `403` everywhere except `/api/auth/me` until an administrator approves them.

### Checks

Run from `backend/` before every pull request (CI runs the same):

```sh
uv run ruff check
uv run ruff format --check
uv run pytest
```

With the development database running, the tests read `.env` and also run the database tests; without it, those tests are skipped locally (in CI they must run).

### Migrations

```sh
uv run alembic revision --autogenerate -m "describe the change"   # then review it by hand
uv run alembic upgrade head          # apply
uv run alembic downgrade -1          # undo the last one
uv run alembic current               # version of the database
uv run alembic upgrade head --sql    # print the SQL without running it
```

Rules for writing migrations: `migrations/README.md`.

### Development database

```sh
docker compose ps                    # status
docker compose logs db               # logs
docker compose stop                  # stop, keeping the data
docker compose down -v               # delete everything, including the data
docker compose exec db psql -U postgres -d sportlab_dev    # SQL shell as superuser
```

The init script (`docker/dev/postgres-init/20_sportlab.sh`) runs only when the data volume is empty: after changing it, or the passwords in `.env`, recreate the database with `docker compose down -v`.

Two roles, as in staging and production:

- `sportlab_dev_migrator` owns the schema and runs Alembic (`DATABASE_MIGRATION_URL`). It also has `CREATEDB`, in development only, for the throwaway databases of the migration tests.
- `sportlab_dev_app` only reads and writes data (`DATABASE_URL`): it cannot create, alter, drop or truncate tables.

`tests/test_db_roles.py` checks this separation on the database the tests use; CI creates the same roles with the same script on its PostgreSQL service.

The `postgis/postgis` image is published for amd64 only: on Apple Silicon it runs under emulation (slower start, same image as CI and production).

## Structure

```
app/
  api/        REST endpoints (sessions, users, activities, metrics, goals, administration)
  core/       configuration, security, key encryption, logging
  db/         connection, session, per-user setting for Row-Level Security
  models/     SQLAlchemy models (user, activity, tracks, metrics, segments, goals, achievements)
  schemas/    API input and output schemas
  services/   application logic, with mandatory per-user filtering
  sync/       sync worker for the Garmin Personal API
migrations/   Alembic migrations
tests/        automated tests
```

## Rules

- Every piece of personal data has a `user_id`; queries only go through `services/` with the authenticated user.
- Row-Level Security in the database as a second barrier, with tests that check one user cannot see another user's data.
- Two database roles per environment: application (data only) and migrations (schema).
- Migrations are reviewed by hand after automatic generation.
- Repeatable seeding: reference data only; no password and no user written in the code.
- Administrator: not a seeded user. The `admin` role is assigned at the first Google login with the address in `ADMIN_EMAIL` (environment variable, never in the repository). An admin can promote or demote other users from the panel; the last admin cannot be removed.

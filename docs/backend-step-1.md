# Backend step 1: minimal backend

Plan for the first piece of code. To be implemented on the Mac with VS Code and Claude Code, one small pull request at a time, so every piece can be reviewed and understood before the next one.

Status: implemented. PR 1 to PR 4 are #15, #16, #17 and #19; PR 5 adds the development Compose. The Bruno collection (#18) was added along the way.

## Goal

A backend that starts, answers a status request, connects to PostgreSQL and has a working migration and test setup. No users, no Garmin, no business logic.

## Out of scope

Authentication, users, Garmin sync, PostGIS tables, the frontend and the MCP server. Each comes in a later step.

## Pull requests

Each item is one pull request towards `staging`, with its own tests and a short explanation of the non-obvious choices.

1. **Project skeleton.** `backend/pyproject.toml` (dependencies, Ruff and pytest settings) and the `uv.lock` lock file, `app/main.py` with a FastAPI application, `GET /api/health` returning `{"status": "ok"}`, and a first test using FastAPI's test client. The CI backend job starts running here because `pyproject.toml` now exists, so this pull request also switches it from `pip install` to `uv` (`astral-sh/setup-uv`, `uv sync`, `uv run`), and adds the `uv` ecosystem to `.github/dependabot.yml`.
2. **Configuration.** `app/core/config.py` reading the variables of `.env.example` with `pydantic-settings`. Missing required values fail at startup with a clear message. Test: defaults, a required variable missing, an override.
3. **Database connection.** `app/db/` with the SQLAlchemy engine and session, using `DATABASE_URL`. `GET /api/health/db` runs `SELECT 1`. Test against a throwaway PostgreSQL (see below).
4. **Alembic.** Alembic set up with `DATABASE_MIGRATION_URL`, an empty first revision, and a test that `upgrade head` and `downgrade base` both work on an empty database.
5. **Local development setup.** A `docker-compose.yml` for development with `postgis/postgis`, the `sportlab_dev` database and the two roles (application and migrations), plus the start commands in `backend/README.md` and the "Commands" section of `CLAUDE.md`.

## Choices to explain while implementing

- Why FastAPI dependencies (`Depends`) provide the database session, and how that makes tests simpler.
- Why there are two database URLs (application role and migration role) and what each role is allowed to do.
- Why the first Alembic revision is empty, and how migrations will stay compatible with the previous code version.
- Why settings are validated at startup and not when first used.

## Tests

- pytest with FastAPI's test client for the HTTP layer.
- A real PostgreSQL for database tests, not a mock: a throwaway database created for the test run. In CI, a `postgres` service container in the backend job. Locally, the development Compose database.
- Style checks: `ruff check` and `ruff format --check`, as already run by CI.

## Definition of done for step 1

- `ruff check backend`, `ruff format --check backend` and `pytest backend/tests` pass locally and in CI.
- `GET /api/health` and `GET /api/health/db` work against the development database.
- `alembic upgrade head` works on an empty database.
- `backend/README.md` and `CLAUDE.md` list the real commands.

## Decisions

- **Python 3.12.** It is the version CI already uses, so development and checks run on the same one. The backend image will be `python:3.12-slim`. A move to a newer version is a separate, later step.
- **`uv` for dependencies.** It creates the virtual environment, installs and locks versions in `uv.lock` (commands: `uv sync`, `uv add`, `uv run pytest`). A lock file makes installs repeatable, which plain `pip` does not give. Dependabot supports it.

## Open points

- PostGIS availability is settled: the dedicated container is running on the homelab (see `postgis.md`). Step 1 itself does not need it; the development Compose uses the `postgis/postgis` image.

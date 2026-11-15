# Backend

REST API, database models, Garmin sync and migrations. Python with FastAPI, SQLAlchemy and Alembic.

Status: structure only; the code arrives in later phases.

## Planned structure

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

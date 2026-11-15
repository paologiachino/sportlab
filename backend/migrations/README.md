# Database migrations

Alembic migrations for the sportlab schema. They run with the migration role
(`DATABASE_MIGRATION_URL`), which owns the schema; the application role
(`DATABASE_URL`) only reads and writes data.

## Rules

- **Compatible with the previous code version.** During a deploy the new schema
  briefly runs with the old code, and a rollback runs the old code on the new
  schema. So a change that would break the old code is split in steps
  ("expand, then contract"):
  1. expand: add the new column or table, nullable or with a default; the old
     code ignores it;
  2. deploy the code that writes both and then reads the new one;
  3. contract, in a later release: drop what the old code needed.
  Renaming a column is therefore add + copy + drop over two releases, never a
  single `ALTER ... RENAME`.
- **Reviewed by hand.** `alembic revision --autogenerate` is a draft: check it
  against the models, add data migrations, and remove anything unintended.
- **Every revision has a working `downgrade()`.** The test suite upgrades and
  downgrades every revision one step at a time on an empty database.
- **One head.** Two revisions with the same parent (from parallel branches)
  are merged with `alembic merge` before the pull request.

#!/bin/sh
# Development database: the sportlab_dev database and its two roles.
# Run once by the postgres image, as superuser, when the data volume is empty
# (after the image's own 10_postgis.sh). CI runs it too, on its PostgreSQL
# service, and backend/tests/test_db_roles.py checks the resulting privileges.
#
#   sportlab_dev_migrator  owns the schema, runs Alembic (DATABASE_MIGRATION_URL)
#   sportlab_dev_app       reads and writes data only (DATABASE_URL)
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v app_password="$SPORTLAB_APP_PASSWORD" \
  -v migrator_password="$SPORTLAB_MIGRATOR_PASSWORD" <<'SQL'
-- CREATEDB in development only: the migration tests create throwaway databases
CREATE ROLE sportlab_dev_migrator LOGIN CREATEDB PASSWORD :'migrator_password';
CREATE ROLE sportlab_dev_app LOGIN PASSWORD :'app_password';

CREATE DATABASE sportlab_dev OWNER sportlab_dev_migrator;
REVOKE ALL ON DATABASE sportlab_dev FROM PUBLIC;
GRANT CONNECT ON DATABASE sportlab_dev TO sportlab_dev_app;

\connect sportlab_dev

-- PostGIS needs a superuser, so it is enabled here rather than in a migration
CREATE EXTENSION IF NOT EXISTS postgis;

-- Only the migrator changes the schema; the application role can use it
ALTER SCHEMA public OWNER TO sportlab_dev_migrator;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO sportlab_dev_app;

-- Tables and sequences the migrator creates later are usable by the application,
-- for data only (no DDL, no TRUNCATE)
ALTER DEFAULT PRIVILEGES FOR ROLE sportlab_dev_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sportlab_dev_app;
ALTER DEFAULT PRIVILEGES FOR ROLE sportlab_dev_migrator IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO sportlab_dev_app;
SQL

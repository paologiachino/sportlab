# PostGIS: check and installation

PostGIS is needed for GPS tracks and segments (maps and segments, phase 3). The official PostgreSQL image does not include it.

Decision: use the existing PostgreSQL container on the homelab, which is empty. Replace the image with `postgis/postgis` (check the available tags on Docker Hub).

## Check

Names in angle brackets must be replaced.

```bash
# container and image
docker ps --format "table {{.Names}}\t{{.Image}}"

# PostgreSQL version
docker exec -it <container> psql -U <user> -d postgres -c "SHOW server_version;"

# is the extension available?
docker exec -it <container> psql -U <user> -d postgres -c "SELECT name, default_version, installed_version FROM pg_available_extensions WHERE name LIKE 'postgis%';"
```

No rows: PostGIS is not installed. With rows: enable it in each database with `CREATE EXTENSION postgis;` and check with `SELECT postgis_full_version();`.

## Procedure

1. Check with `\l` (in `psql`) that PostgreSQL really is empty, and note the major version.
2. Back up as a precaution: `docker exec <container> pg_dumpall -U <user> > backup.sql`, and keep it outside the container.
3. Change the image in the homelab's Docker Compose file to `postgis/postgis` of the desired version. If the major version changes, recreate the data volume (there is no data to keep).
4. Update and restart: `docker compose pull` and `docker compose up -d`.
5. Create the `sportlab_staging` and `sportlab_prod` databases with the application and migration roles, enable PostGIS in each one and verify it.

Installing packages with `apt` inside the container is not recommended: it is lost the first time the container is recreated.

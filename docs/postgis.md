# PostGIS: decision and checks

PostGIS is needed for GPS tracks and segments (maps and segments, phase 3). The official PostgreSQL image does not include it.

## Decision

Sportlab uses a **dedicated container** with the `postgis/postgis` image, not the existing PostgreSQL container of the homelab.

Checked on the homelab: the existing container runs PostgreSQL 17.11 without PostGIS and is **not empty**: it hosts another database (`blog`). Replacing its image would put that data at risk (a different base system can change text ordering and invalidate indexes), so it stays untouched.

The container, its roles and its databases (`sportlab_staging`, `sportlab_prod`) are defined and documented in the [sportlab-infra](https://github.com/paologiachino/sportlab-infra) repository: `database/compose.yml` and `docs/database.md`.

## Checks

Run on the homelab, after starting the dedicated container:

```bash
# PostgreSQL version
docker exec -it sportlab-postgres psql -U postgres -c "SHOW server_version;"

# PostGIS available?
docker exec -it sportlab-postgres psql -U postgres -c "SELECT name, default_version, installed_version FROM pg_available_extensions WHERE name LIKE 'postgis%';"
```

PostGIS must appear in the list. It is enabled in each Sportlab database with `CREATE EXTENSION postgis;` and checked with `SELECT postgis_full_version();` (see `docs/database.md` in `sportlab-infra`).

## Development

Local development uses its own PostGIS container from the development `docker-compose.yml` (backend step 1, see [backend-step-1.md](backend-step-1.md)).

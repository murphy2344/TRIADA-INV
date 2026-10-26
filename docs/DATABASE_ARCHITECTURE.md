# PostgreSQL migration and backup plan

## Intended production topology

- PostgreSQL is intended to be the source of truth for portfolios, user alerts/watchlists, statistics, and recommendation/track-record history.
- Upstash Redis remains responsible for fast deduplication, distributed polling locks, and expiring coordination keys.
- SQLite remains the default storage backend unless `DATABASE_URL` is explicitly configured. Do not configure that variable in production until the rollout checks below are complete.
- A SQLite file on Render's ephemeral filesystem is not durable storage or a verified backup.

## Current implementation and validation

- `modules/db_compat.py` implements the subset of the async SQLite API used by `modules/storage.py`, with PostgreSQL selected by `DATABASE_URL`.
- GitHub Actions starts a disposable PostgreSQL 16 service and runs adapter and application-storage integration tests against it.
- The integration tests validate basic schema creation, read/write operations, duplicate suppression, portfolio upserts, statistics, metadata, and recommendation storage.
- These tests do not prove that the Render staging database is reachable, that live SQLite data has been migrated, or that a production backup can be restored.

## Safe rollout

1. Use a trusted cloud environment to connect to the Render staging database without opening PostgreSQL to all IPs.
2. Obtain a consistent copy of the current SQLite database from the production service. Do not assume the file can be accessed after a redeploy or restart.
3. Run `scripts/migrate_sqlite_to_postgres.py` in dry-run mode against the copy and staging database.
4. Confirm the target is empty, review row counts, run `--apply` only against the staging target, then validate counts and representative records.
5. Exercise the full storage API against the migrated staging data and test a backup/restore into a fresh database.
6. Only after all checks pass, plan a controlled production cutover with a verified backup and rollback path. Avoid silent dual writes without reconciliation.
7. Set `DATABASE_URL` only as part of that planned cutover. Keep the application and database in the same region where possible.

## Migration utility

The script `scripts/migrate_sqlite_to_postgres.py` is deliberately opt-in:
- dry-run is the default and rolls back any schema changes it creates;
- `--apply` makes a timestamped local copy of the source SQLite file first;
- the destination must contain zero rows in the TRIADA tables;
- data copy is transactional and row counts are checked before success is reported.

Run from a trusted environment with both files available:

```bash
export DATABASE_URL='postgresql://...'
python scripts/migrate_sqlite_to_postgres.py --sqlite data/bot.db
python scripts/migrate_sqlite_to_postgres.py --sqlite data/bot.db --apply
```

Never put a database URL or password in source control or logs.

## Current blockers

- The Render staging database's IP allowlist is empty, and the hosted query connection cannot reach it. Do not add `0.0.0.0/0`; use a trusted environment or a temporary cloud test process instead.
- The current production SQLite file has not been copied and migrated to staging as part of this work.
- A successful CI run is not proof of production readiness. Do not switch production to PostgreSQL until staging connectivity, data migration, and backup/restore checks pass.

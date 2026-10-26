# PostgreSQL migration and backup plan

## Intended production topology

- PostgreSQL is the source of truth for portfolios, user alerts/watchlists, statistics, and recommendation/track-record history.
- Upstash Redis remains responsible for fast deduplication, distributed polling locks, and expiring coordination keys.
- SQLite is a local export/restore artifact, not a second independently writable primary database.

## Safe rollout

1. Create PostgreSQL in the same region as the Render app and store its connection string in Render's secret environment settings as `DATABASE_URL`.
2. Keep the application on its existing SQLite path until the PostgreSQL storage adapter is implemented and tested. Do not set `DATABASE_URL` alone as a switch.
3. Take a verified SQLite file copy, run the migration script in dry-run mode, then use `--apply` only against an empty PostgreSQL target.
4. Verify row counts and sample records, then test the adapter against a disposable database and run offline tests.
5. Enable PostgreSQL reads/writes behind an explicit storage mode only after those checks. Keep rollback possible and never silently dual-write without reconciliation.
6. Add scheduled PostgreSQL exports to a separate durable backup location, monitor last-success time, and periodically test restoring into a fresh database. A SQLite file on an ephemeral Render filesystem is not a durable backup by itself.

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

## Current limitations

The migration utility does not switch the running application to PostgreSQL. That requires a separate storage-layer refactor because current application functions issue SQLite-specific SQL directly. Do not treat a successful one-off data migration as proof that production is using PostgreSQL.

# PostgreSQL migration runbook for TRIADA-INV

## Current decision
The PostgreSQL branch has passed the staging smoke test and offline unit tests, but production is not ready to switch. Do not merge this branch as a production migration until the source-data and rollback questions below are resolved.

## Storage inventory from source code
The current SQLite schema in \`modules/storage.py\` has seven application tables:

| Table | Purpose | Migration notes |
|---|---|---|
| \`published_news\` | IDs/titles of published news used for deduplication | Preserve IDs and publication timestamps |
| \`bot_stats\` | Per-day post/error counters | Preserve dates and counters |
| \`recommendations\` | Signals and later track-record outcomes | Preserve IDs, signal metadata, horizon and performance fields |
| \`bot_meta\` | Small key/value state, including alert cooldowns and message IDs | Preserve keys exactly |
| \`user_portfolios\` | User asset positions | Preserve user/ticker uniqueness and average price |
| \`user_alerts\` | Price and smart alerts | Preserve alert IDs, parameters, trigger state |
| \`user_watchlists\` | User ticker watchlists | Preserve user/ticker uniqueness |

This is a code/schema inventory, not a live data inventory. Actual source row counts have not been retrieved.

## Critical source-data blocker
The deployed Render web service is currently on the Free plan, its Blueprint does not configure a persistent disk, and the SQLite path is \`data/bot.db\`. Render documents that a Free web service has an ephemeral filesystem, loses local files on spin-down/restart/redeploy, and does not support SSH or dashboard shell access. Do not deploy a source-inventory endpoint or migration code to this service expecting its local SQLite file to survive the deploy.

Before a real data transfer, establish whether any current SQLite file is recoverable. Never interpret a missing file as an empty, valid source database. The inventory script refuses a missing file and refuses unknown tables or missing columns.

## Script behavior
Run \`scripts/sqlite_to_postgres_migration.py\` only in an environment that actually has the source SQLite file.

- Default invocation is read-only inventory; it prints table counts and schema issues, not row contents.
- \`--apply\` is explicitly opt-in and restricted to the designated Render staging database.
- Import refuses a source-schema mismatch, unmapped source tables, or a destination with existing rows.
- Import and count verification happen in one PostgreSQL transaction; failure rolls back.
- The script preserves explicit IDs and resets identity sequences.
- It is a staging rehearsal tool, not authorization to switch production.

## Safe rollout gates
1. Recover and back up the actual source SQLite file if one exists and still contains required data.
2. Choose a durable production PostgreSQL target. The current Render Free staging database is temporary and expires on 2026-11-25; do not use it as permanent production storage.
3. Run the read-only source inventory and retain a backup outside the service container.
4. Reconcile the source schema and counts. Resolve any unmapped tables or columns before import.
5. Freeze writes for the final copy, run the import to an empty target, and compare row counts, key uniqueness, timestamps, and representative records.
6. Run the staging smoke test and PostgreSQL-specific integration checks on the exact candidate commit.
7. Prepare the production \`DATABASE_URL\`, deploy during a controlled window, verify logs and bot behavior, and keep a documented rollback path. Do not delete or overwrite any source backup.

## What has not been verified
- Whether the running service's current \`data/bot.db\` exists or how many rows it contains.
- Whether the current local SQLite rows can be recovered after prior Free-instance restarts/spin-downs.
- End-to-end operation of every production bot workflow against PostgreSQL.
- A production-grade destination, backups, and rollback procedure.

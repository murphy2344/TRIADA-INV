# Clean PostgreSQL cutover runbook for TRIADA-INV

## Decision
The user has decided not to preserve or import historical SQLite records. The PostgreSQL database will start with a fresh schema and receive new records only. Do not export, copy, or import rows from \`data/bot.db\`.

## What is in the schema
The PostgreSQL migration creates these seven application tables:
- \`published_news\`: new published-news IDs/titles for deduplication.
- \`bot_stats\`: new daily counters.
- \`recommendations\`: new recommendations and subsequent track-record outcomes.
- \`bot_meta\`: new small key/value state, including cooldowns and message IDs.
- \`user_portfolios\`: new portfolio positions.
- \`user_alerts\`: new price and smart alerts.
- \`user_watchlists\`: new watchlist items.

After cutover, counts and history will begin from zero. Existing deduplication history, stored portfolios, alerts, stats, and recommendations from SQLite will not carry over. Upstash Redis is a separate service and is not migrated by this decision.

## Current validation
- User reports the PostgreSQL staging smoke test passed. It initializes the schema and checks core writes/reads.
- User reports offline tests passed, including the latest successful run before removing the old SQLite importer.
- The staging workflow temporarily adds a runner IP to the PostgreSQL allowlist and attempts to restore the original list afterward; the list was checked after the user's run and contained only the user's IPv4 /32.
- The staging target is a temporary Render Free PostgreSQL database and its resource metadata reports an expiration date of 2026-11-25. It must not be treated as the permanent production database.

## Cutover requirements
1. Choose the permanent PostgreSQL target for production. It must be separate from the temporary staging database and have an understood retention/backup plan.
2. Create a new empty database there and set the service's \`DATABASE_URL\` in Render's secret environment settings. Never put the URL/password in the repository, commits, logs, or chat.
3. Verify the environment variable is present only on the intended service and that the current code selects PostgreSQL whenever it sees a \`postgres://\` or \`postgresql://\` URL.
4. Deploy the PostgreSQL-enabled branch only to a safe test service or during an approved maintenance window. Confirm startup logs show PostgreSQL schema initialization completed.
5. Run the staging smoke test against the candidate target and verify published-news, metadata, portfolio upsert/weighted average, alert, watchlist, and recommendation checks.
6. Inspect service logs and behavior after cutover. Keep the old deployment configuration available for rollback, but do not copy old SQLite records.
7. After testing, restore a narrow PostgreSQL IP allowlist. Do not leave \`0.0.0.0/0\` in place.

## Important limitations
- The passing smoke test is focused on core storage operations; it does not prove every bot feature has been exercised against PostgreSQL.
- The current production Render service is on the Free plan and its filesystem is ephemeral. Switching database backend does not fix other local-file persistence concerns, such as Telethon session files, if any are stored on that filesystem.
- Production is not switched by this runbook. The migration pull request remains draft until a permanent target and a controlled cutover plan are confirmed.

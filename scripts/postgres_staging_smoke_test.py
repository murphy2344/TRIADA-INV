"""Non-destructive PostgreSQL staging smoke test for TRIADA-INV.

Run with DATABASE_URL set to the staging database. Creates the schema if absent,
writes a few uniquely named test rows, verifies reads/upserts, then removes them.
Never points at SQLite and refuses to run without a PostgreSQL URL.
"""
import asyncio
import os
import sys
import uuid

# Running from scripts/ puts that directory, not the repository root, at sys.path[0].
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.config import DB_PATH
from modules import db_compat
from modules import storage


async def main():
    url = os.getenv("DATABASE_URL", "").strip()
    if not url.startswith(("postgres://", "postgresql://")):
        raise SystemExit("FAIL: DATABASE_URL must point to the PostgreSQL staging database.")
    if not any(marker in url for marker in (
        "triada_inv_staging",
        "triada_inv_postgres_staging",
        "dpg-dbfpnjvavr4c73fj05ug-a",
    )):
        raise SystemExit(
            "FAIL: refusing to run unless DATABASE_URL clearly identifies a dedicated "
            "TRIADA staging database (triada_inv_staging)."
        )

    print("1/6 PostgreSQL URL detected; initializing schema...")
    await storage.init_db()

    tag = "smoketest-" + uuid.uuid4().hex[:12]
    news_id = tag + "-news"
    ticker = "TST" + uuid.uuid4().hex[:5].upper()
    meta_key = tag + "-meta"
    user_id = int(uuid.uuid4().int % 1_000_000_000) + 1_000_000_000
    print("2/6 Schema initialized.")

    try:
        print("3/6 Testing published-news insert/read and duplicate-safe insert...")
        await storage.mark_published(news_id, tag, "smoke-test", "https://example.invalid/" + tag, "smoke-test")
        if not await storage.is_published(news_id):
            raise RuntimeError("published_news insert/read failed")
        await storage.mark_published(news_id, tag, "smoke-test", "https://example.invalid/" + tag, "smoke-test")
        titles = await storage.get_recent_titles(1)
        if tag not in titles:
            raise RuntimeError("published_news recent-title query failed")

        print("4/6 Testing stats and metadata upsert...")
        # Read stats without mutating the real current-day counters.
        stats = await storage.get_today_stats()
        if not isinstance(stats, dict) or "posts" not in stats:
            raise RuntimeError("bot_stats read failed")
        await storage.set_meta(meta_key, "first")
        await storage.set_meta(meta_key, "second")
        if await storage.get_meta(meta_key) != "second":
            raise RuntimeError("bot_meta upsert failed")

        print("5/6 Testing portfolio, watchlist/alerts, and recommendation write/read...")
        await storage.add_to_portfolio(user_id, ticker, 2.0, 10.0)
        await storage.add_to_portfolio(user_id, ticker, 1.0, 13.0)
        portfolio = await storage.get_portfolio(user_id)
        if (
            len(portfolio) != 1
            or abs(float(portfolio[0]["quantity"]) - 3.0) > 1e-8
            or abs(float(portfolio[0]["avg_price"]) - 11.0) > 1e-8
        ):
            raise RuntimeError(f"portfolio upsert/weighted-average failed: {portfolio!r}")

        await storage.add_alert(user_id, ticker, 12.5, "above")
        await storage.add_smart_alert(user_id, ticker, "smoke-test", {"test": True})
        alerts = await storage.get_user_alerts(user_id)
        if len(alerts) != 2:
            raise RuntimeError(f"alert insert/read failed: {alerts!r}")
        price_alert = next((item for item in alerts if item["alert_type"] == "price"), None)
        smart_alert = next((item for item in alerts if item["alert_type"] == "smoke-test"), None)
        if (
            price_alert is None
            or abs(float(price_alert["target_price"]) - 12.5) > 1e-8
            or price_alert["direction"] != "above"
        ):
            raise RuntimeError(f"price alert fields did not round-trip: {alerts!r}")
        if smart_alert is None or smart_alert["params"] != {"test": True}:
            raise RuntimeError(f"smart alert JSON did not round-trip: {alerts!r}")

        await storage.mark_alert_triggered(price_alert["id"])
        active_for_user = [
            item for item in await storage.get_all_active_alerts()
            if item["user_id"] == user_id
        ]
        if len(active_for_user) != 1 or active_for_user[0]["id"] != smart_alert["id"]:
            raise RuntimeError(f"active-alert filtering/trigger update failed: {active_for_user!r}")
        await storage.delete_alert(user_id, smart_alert["id"])
        if await storage.get_user_alerts(user_id):
            raise RuntimeError("alert delete failed")

        await storage.add_to_watchlist(user_id, ticker)
        await storage.add_to_watchlist(user_id, ticker)
        watchlist = await storage.get_watchlist(user_id)
        if watchlist != [ticker]:
            raise RuntimeError(f"watchlist duplicate-safe insert/read failed: {watchlist!r}")
        await storage.remove_from_watchlist(user_id, ticker)
        if ticker in await storage.get_watchlist(user_id):
            raise RuntimeError("watchlist delete failed")

        await storage.save_recommendation(ticker, tag, "buy", 10.0, category="smoke_test", confidence=0.5, source="smoke-test")
        async with db_compat.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM recommendations WHERE subject = ?", (tag,)
            ) as cur:
                row = await cur.fetchone()
                if not row or row[0] != 1:
                    raise RuntimeError("recommendation insert/read failed")

        print("6/6 Cleaning up smoke-test rows...")
        async with db_compat.connect(DB_PATH) as db:
            await db.execute("DELETE FROM published_news WHERE news_id = ?", (news_id,))
            await db.execute("DELETE FROM user_portfolios WHERE user_id = ?", (user_id,))
            await db.execute("DELETE FROM user_alerts WHERE user_id = ?", (user_id,))
            await db.execute("DELETE FROM user_watchlists WHERE user_id = ?", (user_id,))
            await db.execute("DELETE FROM recommendations WHERE subject = ?", (tag,))
            await db.execute("DELETE FROM bot_meta WHERE key = ?", (meta_key,))
            await db.commit()

        print("PASS: PostgreSQL staging smoke test completed. Schema and core CRUD operations passed.")
    except Exception:
        # Best-effort cleanup of uniquely tagged test data before surfacing the failure.
        try:
            async with db_compat.connect(DB_PATH) as db:
                await db.execute("DELETE FROM published_news WHERE news_id = ?", (news_id,))
                await db.execute("DELETE FROM user_portfolios WHERE user_id = ?", (user_id,))
                await db.execute("DELETE FROM user_alerts WHERE user_id = ?", (user_id,))
                await db.execute("DELETE FROM user_watchlists WHERE user_id = ?", (user_id,))
                await db.execute("DELETE FROM recommendations WHERE subject = ?", (tag,))
                await db.execute("DELETE FROM bot_meta WHERE key = ?", (meta_key,))
                await db.commit()
        except Exception as cleanup_error:
            print(f"WARNING: cleanup also failed: {cleanup_error}")
        raise


if __name__ == "__main__":
    asyncio.run(main())

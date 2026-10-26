"""Exercise the production storage API against the ephemeral CI PostgreSQL service."""
import os
import unittest

from modules import db_compat, storage


@unittest.skipUnless(
    os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://")),
    "DATABASE_URL is not configured for PostgreSQL integration tests",
)
class PostgreSQLStorageIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await storage.init_db()
        async with db_compat.connect(storage.DB_PATH) as db:
            # The CI database is dedicated to tests; clear application rows so
            # tests remain deterministic regardless of unittest execution order.
            for table in (
                "published_news", "bot_stats", "recommendations", "bot_meta",
                "user_portfolios", "user_alerts", "user_watchlists",
            ):
                await db.execute(f'DELETE FROM "{table}"')
            await db.commit()

    async def asyncTearDown(self):
        async with db_compat.connect(storage.DB_PATH) as db:
            for table in (
                "published_news", "bot_stats", "recommendations", "bot_meta",
                "user_portfolios", "user_alerts", "user_watchlists",
            ):
                await db.execute(f'DELETE FROM "{table}"')
            await db.commit()

    async def test_publish_dedup_and_watchlist(self):
        self.assertFalse(await storage.is_published("ci-news-1"))
        await storage.mark_published(
            "ci-news-1", "CI news", "CI", "https://example.invalid/news", "news"
        )
        self.assertTrue(await storage.is_published("ci-news-1"))
        # INSERT OR IGNORE must tolerate a duplicate without breaking the DB.
        await storage.mark_published(
            "ci-news-1", "CI news duplicate", "CI", "https://example.invalid/news", "news"
        )

        await storage.add_to_watchlist(991234, "aapl")
        await storage.add_to_watchlist(991234, "AAPL")
        self.assertEqual(await storage.get_watchlist(991234), ["AAPL"])

    async def test_portfolio_upsert_and_statistics(self):
        await storage.add_to_portfolio(991235, "aapl", 2, 100)
        await storage.add_to_portfolio(991235, "AAPL", 2, 120)
        portfolio = await storage.get_portfolio(991235)
        self.assertEqual(len(portfolio), 1)
        self.assertEqual(portfolio[0]["ticker"], "AAPL")
        self.assertAlmostEqual(portfolio[0]["quantity"], 4)
        self.assertAlmostEqual(portfolio[0]["avg_price"], 110)

        await storage.increment_stats()
        stats = await storage.get_today_stats()
        self.assertEqual(stats["posts"], 1)
        self.assertEqual(stats["errors"], 0)

    async def test_meta_and_recommendation_storage(self):
        await storage.set_meta("ci-key", "ci-value")
        self.assertEqual(await storage.get_meta("ci-key"), "ci-value")

        await storage.save_recommendation(
            ticker="AAPL", subject="CI signal", recommendation="buy",
            price_at_post=100.0, category="market_move", confidence=0.8, source="ci",
        )
        async with db_compat.connect(storage.DB_PATH) as db:
            async with db.execute(
                "SELECT ticker, recommendation, price_at_post, source "
                "FROM recommendations WHERE ticker = ?", ("AAPL",)
            ) as cursor:
                row = await cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "AAPL")
        self.assertEqual(row[1], "buy")
        self.assertAlmostEqual(row[2], 100.0)
        self.assertEqual(row[3], "ci")


if __name__ == "__main__":
    unittest.main()

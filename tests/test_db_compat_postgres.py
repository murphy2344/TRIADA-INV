"""Real PostgreSQL integration tests; enabled only when DATABASE_URL is set."""
import os
import unittest

from modules import db_compat


@unittest.skipUnless(
    os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://")),
    "DATABASE_URL is not set to a PostgreSQL test database",
)
class PostgreSQLCompatibilityIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_context = db_compat.connect(":memory:")
        self.db = await self.db_context.__aenter__()
        await self.db.execute("DROP TABLE IF EXISTS triada_compat_test")
        await self.db.execute(
            "CREATE TABLE triada_compat_test ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "news_id TEXT UNIQUE, title TEXT, "
            "published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        await self.db.commit()

    async def asyncTearDown(self):
        try:
            await self.db.execute("DROP TABLE IF EXISTS triada_compat_test")
            await self.db.commit()
        finally:
            await self.db_context.__aexit__(None, None, None)

    async def test_insert_select_identity_and_conflict_ignore(self):
        await self.db.execute(
            "INSERT OR IGNORE INTO triada_compat_test (news_id, title) VALUES (?, ?)",
            ("news-1", "First"),
        )
        await self.db.execute(
            "INSERT OR IGNORE INTO triada_compat_test (news_id, title) VALUES (?, ?)",
            ("news-1", "Duplicate"),
        )
        await self.db.commit()
        async with self.db.execute(
            "SELECT id, title FROM triada_compat_test WHERE news_id = ?", ("news-1",)
        ) as cursor:
            rows = await cursor.fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], "First")
        self.assertGreater(rows[0][0], 0)

    async def test_pragma_table_info_compatibility(self):
        async with self.db.execute("PRAGMA table_info(triada_compat_test)") as cursor:
            rows = await cursor.fetchall()
        self.assertIn("news_id", {row[1] for row in rows})
        self.assertIn("published_at", {row[1] for row in rows})

    async def test_relative_datetime_query(self):
        await self.db.execute(
            "INSERT INTO triada_compat_test (news_id, title) VALUES (?, ?)",
            ("news-time", "Recent"),
        )
        await self.db.commit()
        async with self.db.execute(
            "SELECT COUNT(*) FROM triada_compat_test "
            "WHERE published_at > datetime('now', ? || ' hours')",
            ("-24",),
        ) as cursor:
            row = await cursor.fetchone()
        self.assertEqual(row[0], 1)


if __name__ == "__main__":
    unittest.main()

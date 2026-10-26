"""Integration tests against a real PostgreSQL server.

CI supplies DATABASE_URL and starts an ephemeral PostgreSQL service. These
tests never connect to the Render staging or production databases.
"""
import os
import unittest

from modules import db_compat


@unittest.skipUnless(
    os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://")),
    "DATABASE_URL is not configured for PostgreSQL integration tests",
)
class PostgreSQLAdapterIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        async with db_compat.connect("unused.sqlite") as db:
            await db.execute("DROP TABLE IF EXISTS triada_ci_compat_test")
            await db.execute(
                """CREATE TABLE triada_ci_compat_test (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            await db.commit()

    async def asyncTearDown(self):
        async with db_compat.connect("unused.sqlite") as db:
            await db.execute("DROP TABLE IF EXISTS triada_ci_compat_test")
            await db.commit()

    async def test_insert_select_conflict_and_pragma_translation(self):
        async with db_compat.connect("unused.sqlite") as db:
            await db.execute(
                "INSERT INTO triada_ci_compat_test (code) VALUES (?)", ("alpha",)
            )
            await db.execute(
                "INSERT OR IGNORE INTO triada_ci_compat_test (code) VALUES (?)", ("alpha",)
            )
            await db.commit()

            async with db.execute(
                "SELECT code FROM triada_ci_compat_test WHERE code = ?", ("alpha",)
            ) as cursor:
                row = await cursor.fetchone()
            self.assertEqual(row[0], "alpha")

            async with db.execute(
                "SELECT COUNT(*) FROM triada_ci_compat_test"
            ) as cursor:
                count = await cursor.fetchone()
            self.assertEqual(count[0], 1)

            async with db.execute(
                "PRAGMA table_info(triada_ci_compat_test)"
            ) as cursor:
                columns = await cursor.fetchall()
            self.assertIn("code", {row[1] for row in columns})

    async def test_relative_time_query_translation(self):
        async with db_compat.connect("unused.sqlite") as db:
            await db.execute(
                "INSERT INTO triada_ci_compat_test (code) VALUES (?)", ("recent",)
            )
            await db.commit()
            async with db.execute(
                "SELECT COUNT(*) FROM triada_ci_compat_test "
                "WHERE created_at > datetime('now', ? || ' hours')",
                ("-1",),
            ) as cursor:
                row = await cursor.fetchone()
            self.assertEqual(row[0], 1)


if __name__ == "__main__":
    unittest.main()

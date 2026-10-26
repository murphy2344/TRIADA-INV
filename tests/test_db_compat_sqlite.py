import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from modules import db_compat


class SQLiteCompatibilityTests(unittest.TestCase):
    def test_sqlite_async_context_and_execute_modes(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as directory:
                path = os.path.join(directory, "test.db")
                # Explicitly test SQLite even when CI also provides DATABASE_URL.
                with patch.object(db_compat, "POSTGRES_ENABLED", False), patch.object(db_compat, "DATABASE_URL", ""):
                    async with db_compat.connect(path) as db:
                        await db.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
                        await db.execute("INSERT INTO sample (value) VALUES (?)", ("works",))
                        await db.commit()
                        async with db.execute("SELECT value FROM sample WHERE id = ?", (1,)) as cursor:
                            row = await cursor.fetchone()
                        self.assertEqual(row[0], "works")
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()

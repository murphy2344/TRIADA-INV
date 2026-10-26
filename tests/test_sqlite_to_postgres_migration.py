import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sqlite_to_postgres_migration.py"
SPEC = importlib.util.spec_from_file_location("sqlite_to_postgres_migration", SCRIPT)
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


class SQLiteInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "bot.db"
        self.conn = sqlite3.connect(self.db_path)
        for table, columns in migration.TABLE_COLUMNS.items():
            definitions = ", ".join(f'"{column}" TEXT' for column in columns)
            self.conn.execute(f'CREATE TABLE "{table}" ({definitions})')
        self.conn.execute(
            'INSERT INTO published_news (id, news_id, title) VALUES (?, ?, ?)',
            (1, "news-1", "Example title"),
        )
        self.conn.commit()
        self.conn.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_inventory_counts_expected_tables_without_printing_rows(self):
        with migration.open_sqlite_readonly(self.db_path) as conn:
            report, problems = migration.inspect_source(conn)
        self.assertEqual(report["published_news"], 1)
        self.assertEqual(sum(report.values()), 1)
        self.assertEqual(problems, [])

    def test_unknown_table_is_reported_instead_of_silently_ignored(self):
        writable = sqlite3.connect(self.db_path)
        writable.execute("CREATE TABLE unknown_metrics (value TEXT)")
        writable.commit()
        writable.close()

        with migration.open_sqlite_readonly(self.db_path) as conn:
            _, problems = migration.inspect_source(conn)
        self.assertTrue(any("unmapped tables: unknown_metrics" in item for item in problems))

    def test_inventory_connection_is_read_only(self):
        with migration.open_sqlite_readonly(self.db_path) as conn:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("DELETE FROM published_news")

    def test_missing_file_is_not_replaced_with_an_empty_database(self):
        missing_path = Path(self.temp_dir.name) / "missing.db"
        with self.assertRaises(FileNotFoundError):
            migration.open_sqlite_readonly(missing_path)


if __name__ == "__main__":
    unittest.main()

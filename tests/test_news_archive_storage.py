import unittest
from unittest.mock import patch

try:
    from modules import storage
except ModuleNotFoundError as exc:
    if exc.name == "aiosqlite":
        raise unittest.SkipTest("SQLite adapter is not installed")
    raise


class FakeDatabase:
    def __init__(self):
        self.statements = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, sql, params=()):
        self.statements.append((sql, params))

    async def commit(self):
        self.committed = True


class NewsArchiveStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_archive_news_items_upserts_only_valid_records(self):
        db = FakeDatabase()
        with patch.object(storage.db_compat, "connect", return_value=db):
            count = await storage.archive_news_items([
                {
                    "id": "news-1", "title": "Fed holds rates",
                    "source": "Publisher", "source_domain": "example.com",
                    "url": "https://example.com/1", "summary": "Summary",
                    "published_at": "2026-10-31T12:00:00+00:00",
                },
                {"id": "", "title": "Missing id"},
            ])

        self.assertEqual(count, 1)
        self.assertTrue(db.committed)
        self.assertEqual(len(db.statements), 1)
        sql, params = db.statements[0]
        self.assertIn("ON CONFLICT(news_id) DO UPDATE", sql)
        self.assertEqual(params[0], "news-1")

    async def test_processing_result_is_saved_as_unicode_json(self):
        db = FakeDatabase()
        analysis = {"summary": "ФРС сохранила ставку", "confidence": 0.82}
        with patch.object(storage.db_compat, "connect", return_value=db):
            await storage.update_news_processing(
                "news-1", "analyzed", analysis=analysis, post_type="BREAKING"
            )

        self.assertTrue(db.committed)
        sql, params = db.statements[0]
        self.assertIn("analysis_json = COALESCE", sql)
        self.assertIn("ФРС", params[1])
        self.assertEqual(params[0], "analyzed")
        self.assertEqual(params[-1], "news-1")


if __name__ == "__main__":
    unittest.main()

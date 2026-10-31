import unittest
from unittest.mock import patch

try:
    from modules import storage, dedup
except ModuleNotFoundError as exc:
    if exc.name == "aiosqlite":
        raise unittest.SkipTest("SQLite adapter is not installed")
    raise


class FakeCursor:
    def __init__(self, database):
        self.database = database

    def __await__(self):
        async def ready():
            return self
        return ready().__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def fetchall(self):
        return self.database.rows


class FakeDatabase:
    def __init__(self):
        self.statements = []
        self.committed = False
        self.rows = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        return FakeCursor(self)

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


class PendingNewsQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_pending_news_restores_source_provenance(self):
        db = FakeDatabase()
        db.rows = [("news-2", "Fed decision", "Publisher", "https://example.com/2",
                    "Summary", "2026-10-31T12:00:00+00:00", 2, '["Publisher A", "Publisher B"]', None)]
        with patch.object(storage.db_compat, "connect", return_value=db):
            items = await storage.get_pending_news(limit=25)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "news-2")
        self.assertEqual(items[0]["source_count"], 2)
        self.assertEqual(items[0]["corroborating_sources"], ["Publisher A", "Publisher B"])
        self.assertIn("processing_status = 'collected'", db.statements[0][0])


class EventFingerprintTests(unittest.TestCase):
    def test_cyrillic_event_subject_produces_nonempty_fingerprint(self):
        fingerprint = dedup._event_fingerprint('ФРС сохранила ключевую ставку', 'macro')
        self.assertEqual(fingerprint, 'macro:фрс сохранила ключевую ставку')

    def test_event_fingerprint_normalizes_punctuation_and_case(self):
        first = dedup._event_fingerprint('Federal Reserve: Holds Rates!', 'macro')
        second = dedup._event_fingerprint('federal reserve holds rates', 'macro')
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

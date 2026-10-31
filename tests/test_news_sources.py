import unittest
from unittest.mock import patch

try:
    from modules import news_sources
except ModuleNotFoundError as exc:
    if exc.name == "feedparser":
        raise unittest.SkipTest("RSS parser is not installed")
    raise


class NewsSourceCorroborationTests(unittest.TestCase):
    def test_similar_headlines_count_distinct_publisher_domains(self):
        items = [
            {
                "title": "Federal Reserve holds interest rates steady after meeting",
                "source": "Publisher A",
                "source_domain": "a.example",
            },
            {
                "title": "Federal Reserve holds interest rates steady after its meeting",
                "source": "Publisher B",
                "source_domain": "b.example",
            },
        ]
        news_sources._attach_corroborating_sources(items)
        self.assertEqual(items[0]["source_count"], 2)
        self.assertEqual(set(items[0]["corroborating_sources"]), {"Publisher A", "Publisher B"})

    def test_same_domain_does_not_count_as_independent_publisher(self):
        items = [
            {
                "title": "Federal Reserve holds interest rates steady after meeting",
                "source": "Publisher A",
                "source_domain": "same.example",
            },
            {
                "title": "Federal Reserve holds interest rates steady after its meeting",
                "source": "Publisher B",
                "source_domain": "same.example",
            },
        ]
        news_sources._attach_corroborating_sources(items)
        self.assertEqual(items[0]["source_count"], 1)


class NewsSourceCacheTests(unittest.TestCase):
    def setUp(self):
        self.source = 'Cache Test'
        self.url = 'https://cache-test.example/feed'
        news_sources._feed_retry_after.pop(self.source, None)
        news_sources._feed_failures.pop(self.source, None)
        news_sources._feed_cache_headers[self.source] = {'If-None-Match': '"v1"'}
        news_sources._host_retry_after.pop('cache-test.example', None)
        news_sources._feed_items_cache[self.source] = [{
            'id': 'cached-id', 'title': 'Cached market headline',
            'source': self.source, 'url': 'https://cache-test.example/story',
            'summary': 'Previously fetched item',
        }]

    def tearDown(self):
        for mapping in (news_sources._feed_retry_after, news_sources._feed_failures,
                        news_sources._feed_cache_headers, news_sources._feed_items_cache,
                        news_sources._feed_last_success, news_sources._host_retry_after):
            mapping.pop(self.source, None)
        news_sources._host_retry_after.pop('cache-test.example', None)

    @patch.object(news_sources.requests, 'get')
    def test_not_modified_response_reuses_last_successful_items(self, get):
        response = type('Response', (), {'status_code': 304, 'headers': {}})()
        get.return_value = response
        items = news_sources._fetch_one(self.source, self.url, 3)
        self.assertEqual([item['id'] for item in items], ['cached-id'])

    @patch.object(news_sources.requests, 'get')
    def test_provider_failure_serves_last_known_good_items(self, get):
        def fail_request():
            raise news_sources.requests.HTTPError('503 unavailable')
        response = type('Response', (), {
            'status_code': 503, 'headers': {}, 'raise_for_status': lambda self: fail_request(),
        })()
        get.return_value = response
        items = news_sources._fetch_one(self.source, self.url, 3)
        self.assertEqual([item['id'] for item in items], ['cached-id'])
        self.assertIn(self.source, news_sources._feed_retry_after)


if __name__ == "__main__":
    unittest.main()

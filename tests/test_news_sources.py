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
                        news_sources._feed_last_success, news_sources._feed_last_status,
                        news_sources._feed_last_error, news_sources._feed_attempts,
                        news_sources._feed_successes, news_sources._host_retry_after):
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


class BreakingNewsQueueReuseTests(unittest.TestCase):
    @patch.object(news_sources, 'fetch_news')
    def test_breaking_filter_reuses_supplied_queue_items(self, fetch_news):
        items = [{'id': 'q1', 'title': 'Company announces earnings', 'summary': '', 'source': 'A'}]
        selected = news_sources.fetch_breaking_news(2, items)
        self.assertEqual(selected, items)
        fetch_news.assert_not_called()


class BreakingNewsPriorityTests(unittest.TestCase):
    def test_urgent_news_is_prioritized_over_routine_earnings(self):
        items = [
            {'id': 'routine', 'title': 'Company reports quarterly earnings', 'summary': '', 'published_at': '2026-10-31T11:00:00Z'},
            {'id': 'urgent', 'title': 'BREAKING: Central bank announces emergency action', 'summary': '', 'published_at': '2026-10-31T10:00:00Z'},
            {'id': 'market', 'title': 'Inflation data released', 'summary': '', 'published_at': '2026-10-31T12:00:00Z'},
        ]
        selected = news_sources.fetch_breaking_news(2, items)
        self.assertEqual([item['id'] for item in selected], ['urgent', 'market'])

    def test_nonbreaking_queue_still_processes_newest_items(self):
        items = [
            {'id': 'older', 'title': 'Company updates product range', 'summary': '', 'published_at': '2026-10-31T10:00:00Z'},
            {'id': 'newer', 'title': 'Company expands office', 'summary': '', 'published_at': '2026-10-31T13:00:00Z'},
        ]
        selected = news_sources.fetch_breaking_news(1, items)
        self.assertEqual([item['id'] for item in selected], ['newer'])


class GlobalMarketScopeTests(unittest.TestCase):
    def test_excludes_russian_equity_market_news(self):
        item = {'title': 'Russia stocks lower at close; MOEX Russia Index unchanged', 'summary': ''}
        self.assertTrue(news_sources.is_excluded_russian_market_story(item))

    def test_excludes_ruble_market_news(self):
        item = {'title': 'Ruble weakens against the dollar', 'summary': ''}
        self.assertTrue(news_sources.is_excluded_russian_market_story(item))

    def test_keeps_geopolitical_news_with_global_market_impact(self):
        item = {'title': 'New sanctions on Russia raise global energy risk', 'summary': ''}
        self.assertFalse(news_sources.is_excluded_russian_market_story(item))


class NewsSourceHealthTests(unittest.TestCase):
    def test_health_reports_per_source_state_without_secrets(self):
        source = next(iter(news_sources.RSS_FEEDS))
        old_values = (
            news_sources._feed_last_status.get(source),
            news_sources._feed_last_error.get(source),
            news_sources._feed_attempts.get(source),
        )
        news_sources._feed_last_status[source] = '503'
        news_sources._feed_last_error[source] = 'HTTP 503'
        news_sources._feed_attempts[source] = 2
        health = news_sources.get_source_health()
        self.assertIn('sources', health)
        self.assertEqual(health['sources'][source]['last_status'], '503')
        self.assertEqual(health['sources'][source]['attempts'], 2)
        self.assertNotIn('token', str(health).lower())
        for mapping, old_value in zip(
            (news_sources._feed_last_status, news_sources._feed_last_error, news_sources._feed_attempts),
            old_values,
        ):
            if old_value is None:
                mapping.pop(source, None)
            else:
                mapping[source] = old_value

    @patch.object(news_sources.requests, 'get')
    def test_finnhub_failure_keeps_last_good_cache(self, get):
        previous_cache = news_sources._finnhub_cache
        news_sources._finnhub_cache = (0.0, [{'id': 'cached', 'title': 'Last good'}])
        get.side_effect = news_sources.requests.HTTPError('503 unavailable')
        with patch.object(news_sources, 'FINNHUB_API_KEY', 'test-key'):
            items = news_sources._fetch_finnhub_general_news()
        self.assertEqual(items[0]['id'], 'cached')
        news_sources._finnhub_cache = previous_cache


if __name__ == "__main__":
    unittest.main()

import unittest

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


if __name__ == "__main__":
    unittest.main()

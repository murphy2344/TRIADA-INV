import unittest
from unittest.mock import patch

try:
    from modules import ai_analyzer
except ModuleNotFoundError as exc:
    if exc.name in {"requests", "groq"}:
        raise unittest.SkipTest(f"AI analyzer dependencies are not installed: {exc.name}")
    raise


class AIFilterTests(unittest.TestCase):
    def test_obvious_sports_headline_skips_without_ai(self):
        self.assertTrue(
            ai_analyzer._obviously_nonfinancial("Футбольный матч завершился со счетом 2:1")
        )

    def test_financial_news_is_not_skipped_by_sports_gate(self):
        self.assertFalse(
            ai_analyzer._obviously_nonfinancial(
                "Футбольный клуб сообщил о выручке и росте акций материнской компании"
            )
        )

    def test_duplicate_titles_are_detected(self):
        previous = [(ai_analyzer._title_key("Fed holds rates steady"),
                     ai_analyzer._title_tokens("Fed holds rates steady"))]
        self.assertTrue(
            ai_analyzer._is_local_duplicate("Fed holds rates steady!", previous)
        )

    def test_distinct_titles_are_not_duplicates(self):
        previous = [(ai_analyzer._title_key("ECB cuts interest rates"),
                     ai_analyzer._title_tokens("ECB cuts interest rates"))]
        self.assertFalse(
            ai_analyzer._is_local_duplicate("Oil prices jump after supply disruption", previous)
        )


class AIFailoverTests(unittest.TestCase):
    @patch.object(ai_analyzer, "_analyze_groq")
    @patch.object(ai_analyzer, "_analyze_gemini")
    def test_failover_is_bounded_and_stops_on_success(self, gemini, groq):
        gemini.return_value = None
        groq.side_effect = [None, {"relevant": True, "title": "test"}]
        with patch.object(ai_analyzer, "GEMINI_API_KEY", "test-key"), \
             patch.object(ai_analyzer, "GROQ_API_KEY", "test-key"), \
             patch.object(ai_analyzer, "PRIMARY_GROQ_MODEL", "model-a"), \
             patch.object(ai_analyzer, "SECONDARY_GROQ_MODEL", "model-b"):
            result = ai_analyzer.analyze("Central bank announces policy decision")

        self.assertEqual(result, {"relevant": True, "title": "test"})
        self.assertEqual(groq.call_count, 2)
        self.assertEqual([call.args[2] for call in groq.call_args_list], ["model-a", "model-b"])

    @patch.object(ai_analyzer, "_analyze_gemini")
    def test_obvious_nonfinancial_item_uses_no_provider(self, gemini):
        with patch.object(ai_analyzer, "GEMINI_API_KEY", "test-key"), \
             patch.object(ai_analyzer, "GROQ_API_KEY", "test-key"), \
             patch.object(ai_analyzer, "_analyze_groq") as groq:
            result = ai_analyzer.analyze("Премьера фильма состоялась вчера")

        self.assertFalse(result["relevant"])
        gemini.assert_not_called()
        groq.assert_not_called()


if __name__ == "__main__":
    unittest.main()

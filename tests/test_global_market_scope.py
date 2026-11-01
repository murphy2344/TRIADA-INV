import unittest
from unittest.mock import Mock, patch

from modules import charting, technical_alerts


class GlobalMarketScopeTests(unittest.TestCase):
    def test_automated_technical_watchlist_contains_no_russian_instruments(self):
        self.assertFalse(
            any(ticker.endswith(".ME") for ticker in technical_alerts.WATCHLIST),
            technical_alerts.WATCHLIST,
        )


class ChartImgRateLimitTests(unittest.TestCase):
    def setUp(self):
        charting._CHART_IMG_LAST_REQUEST_AT = 0.0
        charting._CHART_IMG_COOLDOWN_UNTIL = 0.0

    def tearDown(self):
        charting._CHART_IMG_LAST_REQUEST_AT = 0.0
        charting._CHART_IMG_COOLDOWN_UNTIL = 0.0

    @patch.object(charting, "CHART_IMG_API_KEY", "unit-test-secret")
    @patch.object(charting.time, "monotonic", return_value=100.0)
    @patch.object(charting, "requests")
    def test_http_429_activates_global_cooldown_for_other_symbols(
        self, requests_mock, _clock
    ):
        response = Mock()
        response.ok = False
        response.status_code = 429
        response.headers = {"Content-Type": "application/json"}
        response.json.return_value = {"message": "rate limit exceeded"}
        requests_mock.get.return_value = response

        self.assertIsNone(charting._chart_img("AAPL"))
        self.assertIsNone(charting._chart_img("MSFT"))

        requests_mock.get.assert_called_once()
        self.assertGreater(charting._CHART_IMG_COOLDOWN_UNTIL, 100.0)


if __name__ == "__main__":
    unittest.main()

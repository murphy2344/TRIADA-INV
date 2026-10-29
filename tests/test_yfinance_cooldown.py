import sys
import logging
import types
import unittest
from unittest.mock import Mock, patch

from modules import charting


class YahooPriceCooldownTests(unittest.TestCase):
    def setUp(self):
        self.old_state = (
            charting._YFINANCE_COOLDOWN_UNTIL,
            charting._YFINANCE_COOLDOWN_REASON,
            charting._YFINANCE_COOLDOWN_LOGGED,
        )
        charting._YFINANCE_COOLDOWN_UNTIL = 0.0
        charting._YFINANCE_COOLDOWN_REASON = ""
        charting._YFINANCE_COOLDOWN_LOGGED = False

    def tearDown(self):
        (
            charting._YFINANCE_COOLDOWN_UNTIL,
            charting._YFINANCE_COOLDOWN_REASON,
            charting._YFINANCE_COOLDOWN_LOGGED,
        ) = self.old_state

    def test_rate_limit_starts_long_cooldown_and_skips_followup_request(self):
        ticker = Mock()
        ticker.history.side_effect = RuntimeError("HTTP 429 Too Many Requests")
        provider = types.SimpleNamespace(Ticker=Mock(return_value=ticker))

        with patch.dict(sys.modules, {"yfinance": provider}):
            self.assertIsNone(charting._fetch_yfinance_history("AAPL", "1d"))
            self.assertGreater(charting._YFINANCE_COOLDOWN_UNTIL, 0)
            with patch.object(charting.time, "monotonic", return_value=charting._YFINANCE_COOLDOWN_UNTIL - 1):
                self.assertIsNone(charting._fetch_yfinance_history("MSFT", "1d"))

        ticker.history.assert_called_once_with(period="1d")
        self.assertEqual(charting._YFINANCE_COOLDOWN_REASON, "rate/auth limit")

    def test_crumb_429_log_starts_rate_limit_cooldown_even_when_history_returns_data(self):
        data = Mock()
        data.empty = False
        ticker = Mock()

        def history(**kwargs):
            logging.getLogger("yfinance").warning(
                "Crumb fetch rate-limited (HTTP 429), continuing without crumb"
            )
            return data

        ticker.history.side_effect = history
        provider = types.SimpleNamespace(Ticker=Mock(return_value=ticker))

        with patch.dict(sys.modules, {"yfinance": provider}):
            result = charting._fetch_yfinance_history("SPY", "1d")

        self.assertIsNone(result)
        self.assertEqual(charting._YFINANCE_COOLDOWN_REASON, "crumb rate limit")
        self.assertGreaterEqual(
            charting._YFINANCE_COOLDOWN_UNTIL - charting.time.monotonic(),
            charting._YFINANCE_RATE_LIMIT_SECONDS - 2,
        )
        ticker.history.assert_called_once_with(period="1d")

    def test_yfinance_401_invalid_crumb_log_starts_rate_limit_cooldown(self):
        data = Mock()
        data.empty = False
        ticker = Mock()

        def history(**kwargs):
            logging.getLogger("yfinance").error(
                'HTTP Error 401: {"error":{"description":"Invalid Crumb"}}'
            )
            return data

        ticker.history.side_effect = history
        provider = types.SimpleNamespace(Ticker=Mock(return_value=ticker))

        with patch.dict(sys.modules, {"yfinance": provider}):
            result = charting._fetch_yfinance_history("SPY", "1d")

        self.assertIsNone(result)
        self.assertEqual(charting._YFINANCE_COOLDOWN_REASON, "crumb rate limit")
        self.assertGreaterEqual(
            charting._YFINANCE_COOLDOWN_UNTIL - charting.time.monotonic(),
            charting._YFINANCE_RATE_LIMIT_SECONDS - 2,
        )
        ticker.history.assert_called_once_with(period="1d")

    def test_ranged_history_uses_start_and_end_without_period(self):
        data = Mock()
        data.empty = False
        ticker = Mock()
        ticker.history.return_value = data
        provider = types.SimpleNamespace(Ticker=Mock(return_value=ticker))

        with patch.dict(sys.modules, {"yfinance": provider}):
            result = charting._fetch_yfinance_history(
                "AAPL", start="2024-01-01", end="2024-02-01"
            )

        self.assertIs(result, data)
        ticker.history.assert_called_once_with(
            start="2024-01-01", end="2024-02-01"
        )

    def test_empty_history_starts_short_cooldown(self):
        empty = Mock()
        empty.empty = True
        ticker = Mock()
        ticker.history.return_value = empty
        provider = types.SimpleNamespace(Ticker=Mock(return_value=ticker))

        with patch.dict(sys.modules, {"yfinance": provider}):
            self.assertIsNone(charting._fetch_yfinance_history("GC=F", "1d"))

        self.assertEqual(charting._YFINANCE_COOLDOWN_REASON, "empty history")
        self.assertGreater(charting._YFINANCE_COOLDOWN_UNTIL, 0)

    def test_successful_history_clears_previous_cooldown(self):
        data = Mock()
        data.empty = False
        ticker = Mock()
        ticker.history.return_value = data
        provider = types.SimpleNamespace(Ticker=Mock(return_value=ticker))
        charting._YFINANCE_COOLDOWN_UNTIL = 9999999999.0
        charting._YFINANCE_COOLDOWN_REASON = "old failure"

        with patch.dict(sys.modules, {"yfinance": provider}):
            # Expire cooldown first so the request can run.
            charting._YFINANCE_COOLDOWN_UNTIL = 0.0
            result = charting._fetch_yfinance_history("AAPL", "1d")

        self.assertIs(result, data)
        self.assertEqual(charting._YFINANCE_COOLDOWN_UNTIL, 0.0)
        self.assertEqual(charting._YFINANCE_COOLDOWN_REASON, "")


    def test_sparkline_uses_shared_cooldown_instead_of_download(self):
        charting._YFINANCE_COOLDOWN_UNTIL = 9999999999.0
        with patch.object(charting, "_fetch_yfinance_history", return_value=None) as fetch:
            result = charting.get_sparkline_data("AAPL")
        self.assertIsNone(result)
        fetch.assert_called_once_with("AAPL", period="5d", interval="1h")

    def test_alert_price_fetch_uses_shared_current_price_helper(self):
        # Stub optional storage modules so this focused unit test does not
        # require database dependencies in the offline test workflow.
        storage_stub = types.ModuleType("modules.storage")
        smart_alerts_stub = types.ModuleType("modules.smart_alerts")
        with patch.dict(sys.modules, {
            "modules.storage": storage_stub,
            "modules.smart_alerts": smart_alerts_stub,
        }):
            from modules import alert_checker
            with patch.object(charting, "get_current_price", side_effect=[123.4, None]) as fetch:
                result = alert_checker._fetch_prices(["AAPL", "MSFT"])
        self.assertEqual(result, {"AAPL": 123.4, "MSFT": None})
        self.assertEqual(fetch.call_count, 2)


if __name__ == "__main__":
    unittest.main()

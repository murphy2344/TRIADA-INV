import unittest

try:
    from modules import formatter
except ModuleNotFoundError as exc:
    if exc.name in {"telegram", "pytz"}:
        raise unittest.SkipTest(f"Formatter dependencies are not installed: {exc.name}")
    raise


class TrackRecordDirectionTests(unittest.TestCase):
    def test_short_signal_reports_positive_return_when_price_falls(self):
        text = formatter.fmt_track_record_result([{
            "ticker": "AAPL",
            "recommendation": "short",
            "price_at_post": 100.0,
            "price_after": 90.0,
            "pnl_percent": 10.0,
            "correct": True,
            "horizon_hours": 48,
        }])
        self.assertIn("доходность по направлению: <code>+10.00%</code>", text)
        self.assertIn("горизонт 48 ч", text)

    def test_long_signal_reports_negative_return_when_price_falls(self):
        text = formatter.fmt_track_record_result([{
            "ticker": "AAPL",
            "recommendation": "long",
            "price_at_post": 100.0,
            "price_after": 90.0,
            "pnl_percent": -10.0,
            "correct": False,
            "horizon_hours": 24,
        }])
        self.assertIn("доходность по направлению: <code>-10.00%</code>", text)

    def test_short_fallback_calculation_is_directional(self):
        text = formatter.fmt_track_record_result([{
            "ticker": "AAPL",
            "recommendation": "short",
            "price_at_post": 100.0,
            "price_after": 90.0,
            "correct": True,
        }])
        self.assertIn("доходность по направлению: <code>+10.00%</code>", text)


if __name__ == "__main__":
    unittest.main()

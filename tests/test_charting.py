import unittest
from unittest.mock import Mock, patch

try:
    from modules import charting
except ModuleNotFoundError as exc:
    if exc.name in {"requests", "matplotlib", "yfinance"}:
        raise unittest.SkipTest(f"Charting dependencies are not installed: {exc.name}")
    raise


class ChartImgTests(unittest.TestCase):
    @patch.object(charting, "requests")
    @patch.object(charting, "CHART_IMG_API_KEY", "unit-test-secret")
    def test_v1_uses_bearer_auth_and_does_not_send_v2_api_key_header(self, requests_mock):
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.headers = {"Content-Type": "image/png"}
        response.content = b"\x89PNG\r\n\x1a\nvalid-test-image"
        requests_mock.get.return_value = response

        result = charting._chart_img("AAPL")

        self.assertEqual(result, response.content)
        kwargs = requests_mock.get.call_args.kwargs
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer unit-test-secret",
        )
        self.assertNotIn("x-api-key", kwargs["headers"])

    @patch.object(charting, "requests")
    @patch.object(charting, "CHART_IMG_API_KEY", "unit-test-secret")
    def test_403_logs_safe_json_detail_without_api_key(self, requests_mock):
        response = Mock()
        response.ok = False
        response.status_code = 403
        response.headers = {"Content-Type": "application/json; charset=utf-8"}
        response.json.return_value = {"message": "invalid API key"}
        response.content = b'{"message":"invalid API key"}'
        requests_mock.get.return_value = response

        with self.assertLogs(charting.logger, level="WARNING") as captured:
            result = charting._chart_img("AAPL")

        self.assertIsNone(result)
        log_text = " ".join(captured.output)
        self.assertIn("HTTP 403", log_text)
        self.assertIn("invalid API key", log_text)
        self.assertNotIn("unit-test-secret", log_text)

    @patch.object(charting, "requests")
    @patch.object(charting, "CHART_IMG_API_KEY", "unit-test-secret")
    def test_successful_status_with_non_image_body_is_rejected(self, requests_mock):
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.headers = {"Content-Type": "application/json"}
        response.content = b'{"error":"not an image"}'
        response.json.return_value = {"error": "not an image"}
        requests_mock.get.return_value = response

        result = charting._chart_img("AAPL")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

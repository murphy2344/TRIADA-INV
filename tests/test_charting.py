import unittest
from unittest.mock import Mock, patch

try:
    from modules import charting
except ModuleNotFoundError as exc:
    if exc.name in {"requests", "matplotlib", "yfinance"}:
        raise unittest.SkipTest(f"Charting dependencies are not installed: {exc.name}")
    raise


class ChartImgTests(unittest.TestCase):

    def test_chart_img_uses_tradingview_symbols_for_yahoo_futures_and_fx(self):
        self.assertEqual(charting.chart_img_symbol("CL=F"), "NYMEX:CL1!")
        self.assertEqual(charting.chart_img_symbol("GC=F"), "COMEX:GC1!")
        self.assertEqual(charting.chart_img_symbol("EURUSD=X"), "FX:EURUSD")
        self.assertEqual(charting.chart_img_symbol("JPY=X"), "FX:USDJPY")
        self.assertEqual(charting.chart_img_symbol("AAPL"), "NASDAQ:AAPL")

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


class PhotoProviderChainTests(unittest.IsolatedAsyncioTestCase):
    async def test_rss_image_has_highest_priority(self):
        from modules import media
        with patch.object(media, "_wikimedia_commons", new=__import__("unittest").mock.AsyncMock()) as commons:
            result = await media.get_photo("Company earnings", rss_image="https://example.test/rss.jpg")
        self.assertEqual(result, "https://example.test/rss.jpg")
        commons.assert_not_awaited()

    async def test_all_five_remote_providers_are_tried_in_priority_order(self):
        from modules import media
        from unittest.mock import AsyncMock
        providers = ["_wikimedia_commons", "_wikipedia_pageimage", "_google_cse", "_pexels", "_pixabay"]
        for selected_index, selected_provider in enumerate(providers):
            with self.subTest(provider=selected_provider):
                patches = []
                for index, name in enumerate(providers):
                    value = f"https://images.example/{name}.jpg" if index == selected_index else None
                    patches.append(patch.object(media, name, new=AsyncMock(return_value=value)))
                try:
                    mocks = [p.start() for p in patches]
                    result = await media.get_photo("Market news", subject_en="Market news")
                    self.assertEqual(result, f"https://images.example/{selected_provider}.jpg")
                    for index, mock in enumerate(mocks):
                        self.assertEqual(mock.await_count, 1 if index <= selected_index else 0)
                finally:
                    for p in reversed(patches):
                        p.stop()

    async def test_local_stub_is_used_when_all_providers_fail(self):
        from modules import media
        from unittest.mock import AsyncMock
        with patch.object(media, "_wikimedia_commons", new=AsyncMock(return_value=None)), \
             patch.object(media, "_wikipedia_pageimage", new=AsyncMock(return_value=None)), \
             patch.object(media, "_google_cse", new=AsyncMock(return_value=None)), \
             patch.object(media, "_pexels", new=AsyncMock(return_value=None)), \
             patch.object(media, "_pixabay", new=AsyncMock(return_value=None)), \
             patch.object(media, "_load_stub_file", return_value=b"stub-image"):
            result = await media.get_photo("Market news")
        self.assertEqual(result, b"stub-image")


class RemotePhotoSendTests(unittest.IsolatedAsyncioTestCase):
    async def test_remote_url_is_downloaded_and_uploaded_as_bytes(self):
        from modules import telegram_sender
        from unittest.mock import AsyncMock
        bot = AsyncMock()
        image = b"\x89PNG\r\n\x1a\nunit-test-image"
        with patch.object(telegram_sender, "_download_remote_image", new=AsyncMock(return_value=image)) as download:
            ok, detail = await telegram_sender.send_photo_text_detailed(
                bot, "https://images.example/test.png", "Market update", chat_id="-100123"
            )
        self.assertTrue(ok)
        self.assertEqual(detail, "")
        download.assert_awaited_once_with("https://images.example/test.png")
        self.assertEqual(bot.send_photo.await_args.kwargs["photo"], image)
        bot.send_message.assert_not_awaited()

    async def test_remote_download_timeout_falls_back_to_text(self):
        from modules import telegram_sender
        from unittest.mock import AsyncMock
        bot = AsyncMock()
        with patch.object(telegram_sender, "_download_remote_image", new=AsyncMock(side_effect=TimeoutError("host timeout"))):
            ok, detail = await telegram_sender.send_photo_text_detailed(
                bot, "https://images.example/test.png", "Market update", chat_id="-100123"
            )
        self.assertTrue(ok)
        self.assertIn("text fallback succeeded", detail)
        bot.send_photo.assert_not_awaited()
        self.assertEqual(bot.send_message.await_args.kwargs["text"], "Market update")

    async def test_long_caption_is_sent_separately_after_photo(self):
        from modules import telegram_sender
        from unittest.mock import AsyncMock
        bot = AsyncMock()
        caption = "x" * 1100
        with patch.object(telegram_sender, "_download_remote_image", new=AsyncMock(return_value=b"\xff\xd8\xffimage")):
            ok, detail = await telegram_sender.send_photo_text_detailed(
                bot, "https://images.example/test.jpg", caption, chat_id="-100123"
            )
        self.assertTrue(ok)
        self.assertEqual(detail, "")
        self.assertEqual(bot.send_photo.await_args.kwargs["caption"], "")
        self.assertEqual(bot.send_message.await_args.kwargs["text"], caption)


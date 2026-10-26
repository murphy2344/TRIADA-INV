import unittest
from unittest.mock import AsyncMock

from modules.telegram_sender import send_photo_text_detailed


class TelegramSenderCaptionTests(unittest.IsolatedAsyncioTestCase):
    async def test_long_photo_caption_is_sent_as_followup_message(self):
        bot = AsyncMock()
        markup = object()
        caption = "<b>" + ("market " * 180) + "</b>"

        ok, detail = await send_photo_text_detailed(
            bot, b"fake-image-bytes", caption,
            chat_id="@test-channel", reply_markup=markup,
        )

        self.assertTrue(ok, detail)
        bot.send_photo.assert_awaited_once()
        photo_kwargs = bot.send_photo.await_args.kwargs
        self.assertEqual(photo_kwargs["caption"], "")
        self.assertIs(photo_kwargs["reply_markup"], markup)

        bot.send_message.assert_awaited_once()
        text_kwargs = bot.send_message.await_args.kwargs
        self.assertEqual(text_kwargs["text"], caption)
        self.assertNotIn("reply_markup", text_kwargs)

    async def test_caption_at_telegram_limit_stays_on_photo(self):
        bot = AsyncMock()
        caption = "x" * 1024

        ok, detail = await send_photo_text_detailed(
            bot, b"fake-image-bytes", caption, chat_id="@test-channel",
        )

        self.assertTrue(ok, detail)
        bot.send_photo.assert_awaited_once()
        self.assertEqual(bot.send_photo.await_args.kwargs["caption"], caption)
        bot.send_message.assert_not_awaited()

    async def test_short_photo_caption_stays_on_photo_with_buttons(self):
        bot = AsyncMock()
        markup = object()
        caption = "<b>Market update</b>"

        ok, detail = await send_photo_text_detailed(
            bot, b"fake-image-bytes", caption,
            chat_id="@test-channel", reply_markup=markup,
        )

        self.assertTrue(ok, detail)
        bot.send_photo.assert_awaited_once()
        self.assertEqual(bot.send_photo.await_args.kwargs["caption"], caption)
        self.assertIs(bot.send_photo.await_args.kwargs["reply_markup"], markup)
        bot.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

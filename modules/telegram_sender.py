import logging
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
from config.config import CHANNEL_ID

logger = logging.getLogger(__name__)

async def send_text(bot: Bot, text: str, chat_id: str = None) -> bool:
    cid = chat_id or CHANNEL_ID
    try:
        await bot.send_message(chat_id=cid, text=text, parse_mode=ParseMode.HTML,
                               disable_web_page_preview=False)
        return True
    except TelegramError as e:
        logger.error(f"send_text error: {e}")
        return False

async def send_photo_text(bot: Bot, media, caption: str, chat_id: str = None) -> bool:
    cid = chat_id or CHANNEL_ID
    try:
        if isinstance(media, bytes):
            await bot.send_photo(chat_id=cid, photo=media, caption=caption,
                                 parse_mode=ParseMode.HTML)
        elif isinstance(media, str) and media.startswith("http"):
            await bot.send_photo(chat_id=cid, photo=media, caption=caption,
                                 parse_mode=ParseMode.HTML)
        elif isinstance(media, str) and media.endswith((".jpg", ".jpeg", ".png")):
            with open(media, "rb") as f:
                await bot.send_photo(chat_id=cid, photo=f, caption=caption,
                                     parse_mode=ParseMode.HTML)
        else:
            await bot.send_message(chat_id=cid, text=caption, parse_mode=ParseMode.HTML)
        return True
    except TelegramError as e:
        logger.error(f"send_photo error: {e}")
        try:
            await bot.send_message(chat_id=cid, text=caption, parse_mode=ParseMode.HTML)
            return True
        except Exception:
            return False

async def send_two_messages(bot: Bot, media, caption1: str, text2: str, chat_id: str = None) -> bool:
    ok1 = await send_photo_text(bot, media, caption1, chat_id)
    ok2 = await send_text(bot, text2, chat_id)
    return ok1 and ok2

async def notify_admin(bot: Bot, admin_id: str, message: str):
    if not admin_id:
        return
    try:
        await bot.send_message(chat_id=admin_id, text=message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Admin notify error: {e}")

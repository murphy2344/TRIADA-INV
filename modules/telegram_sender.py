import html
import logging
import re
import aiohttp
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
from config.config import CHANNEL_ID, GROUP_CHAT_ID


def _default_chat_id() -> str:
    value = GROUP_CHAT_ID or CHANNEL_ID
    return str(value or "").strip().strip('"').strip("'")


logger = logging.getLogger(__name__)


MAX_REMOTE_IMAGE_BYTES = 10 * 1024 * 1024


async def _download_remote_image(url: str) -> bytes:
    """Download and validate remote images before uploading them to Telegram.

    Telegram fetching third-party URLs can time out or reject inaccessible URLs.
    Downloading here lets us validate the response and upload known image bytes.
    """
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        raise ValueError("Unsupported image URL")

    timeout = aiohttp.ClientTimeout(total=12, connect=5, sock_read=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, allow_redirects=True) as response:
            if response.status != 200:
                raise ValueError(f"Image host returned HTTP {response.status}")
            if not response.headers.get("Content-Type", "").lower().startswith("image/"):
                raise ValueError("Remote URL did not return an image content type")
            if response.content_length and response.content_length > MAX_REMOTE_IMAGE_BYTES:
                raise ValueError("Remote image exceeds 10 MB limit")

            chunks = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                chunks.extend(chunk)
                if len(chunks) > MAX_REMOTE_IMAGE_BYTES:
                    raise ValueError("Remote image exceeds 10 MB limit")

            data = bytes(chunks)
            signatures = (
                data.startswith(b"\x89PNG\r\n\x1a\n"),
                data.startswith(b"\xff\xd8\xff"),
                data.startswith((b"GIF87a", b"GIF89a")),
                len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
            )
            if not any(signatures):
                raise ValueError("Remote response is not a supported image file")
            logger.info("Remote photo downloaded and validated: bytes=%d content_type=%s", len(data), response.headers.get("Content-Type", "unknown"))
            return data


def _plain_text(text: str) -> str:
    """Remove Telegram HTML tags for a last-resort text-only delivery."""
    text = html.unescape(str(text or ""))
    return re.sub(r"<[^>]*>", "", text)


def _thread_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        phrase in text
        for phrase in (
            "message thread not found",
            "thread not found",
            "topic not found",
            "message thread id invalid",
        )
    )


async def _recover_forum_topic(bot, chat_id: str, topic_key: str | None, stale_id: int | None) -> int | None:
    if not topic_key or str(chat_id).strip() != str(GROUP_CHAT_ID).strip():
        return None
    try:
        from modules import forum_topics
        return await forum_topics.recreate_topic(bot, chat_id, topic_key, stale_id)
    except Exception as exc:
        logger.exception("Forum topic recovery failed for %s: %s", topic_key, exc)
        return None


async def send_text(
    bot: Bot,
    text: str,
    chat_id: str = None,
    message_thread_id: int | None = None,
    topic_key: str | None = None,
) -> bool:
    cid = chat_id or _default_chat_id()
    kwargs = {"message_thread_id": message_thread_id} if message_thread_id is not None else {}
    try:
        await bot.send_message(
            chat_id=cid, text=text, parse_mode=ParseMode.HTML,
            disable_web_page_preview=False, **kwargs,
        )
        return True
    except TelegramError as exc:
        if message_thread_id is not None and _thread_error(exc):
            new_id = await _recover_forum_topic(bot, cid, topic_key, message_thread_id)
            if new_id is None:
                logger.error("Forum topic %s is unavailable and could not be recreated", message_thread_id)
                return False
            try:
                await bot.send_message(
                    chat_id=cid, text=text, parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False, message_thread_id=new_id,
                )
                return True
            except TelegramError as retry_exc:
                logger.error("Forum topic retry failed after recreation: %s", retry_exc)
                return False
        logger.error("send_text error: %s", exc)
        try:
            await bot.send_message(
                chat_id=cid, text=_plain_text(text),
                disable_web_page_preview=False, **kwargs,
            )
            return True
        except TelegramError:
            return False


async def send_photo_text(bot: Bot, media, caption: str, chat_id: str = None, message_thread_id: int | None = None, topic_key: str | None = None) -> bool:
    ok, _ = await send_photo_text_detailed(
        bot, media, caption, chat_id=chat_id,
        message_thread_id=message_thread_id, topic_key=topic_key,
    )
    return ok


async def send_photo_text_detailed(
    bot: Bot,
    media,
    caption: str,
    chat_id: str = None,
    message_thread_id: int | None = None,
    topic_key: str | None = None,
    reply_markup=None,
) -> tuple[bool, str]:
    """Send media and recover a deleted forum topic once when necessary."""
    cid = chat_id or _default_chat_id()
    kwargs = {"message_thread_id": message_thread_id} if message_thread_id is not None else {}

    async def send_once():
        is_photo = (
            isinstance(media, bytes)
            or (isinstance(media, str) and media.startswith("http"))
            or (isinstance(media, str) and media.endswith((".jpg", ".jpeg", ".png")))
        )

        # Telegram limits photo captions to 1024 characters, while regular
        # messages allow up to 4096. Keep long BREAKING analysis readable:
        # attach controls to the photo and send the full HTML text separately.
        split_caption = is_photo and len(caption) > 1024
        photo_caption = "" if split_caption else caption

        if isinstance(media, bytes):
            await bot.send_photo(chat_id=cid, photo=media, caption=photo_caption,
                                 parse_mode=ParseMode.HTML, reply_markup=reply_markup,
                                 connect_timeout=10, read_timeout=30, write_timeout=30,
                                 pool_timeout=10, **kwargs)
            logger.info("Telegram photo sent successfully: source=bytes")
        elif isinstance(media, str) and media.startswith(("https://", "http://")):
            image_bytes = await _download_remote_image(media)
            logger.info("Uploading downloaded photo to Telegram: bytes=%d", len(image_bytes))
            await bot.send_photo(chat_id=cid, photo=image_bytes, caption=photo_caption,
                                 parse_mode=ParseMode.HTML, reply_markup=reply_markup,
                                 connect_timeout=10, read_timeout=30, write_timeout=30,
                                 pool_timeout=10, **kwargs)
            logger.info("Telegram photo sent successfully: source=remote_download bytes=%d", len(image_bytes))
        elif isinstance(media, str) and media.endswith((".jpg", ".jpeg", ".png")):
            with open(media, "rb") as f:
                await bot.send_photo(chat_id=cid, photo=f, caption=photo_caption,
                                     parse_mode=ParseMode.HTML, reply_markup=reply_markup,
                                     connect_timeout=10, read_timeout=30, write_timeout=30,
                                     pool_timeout=10, **kwargs)
                logger.info("Telegram photo sent successfully: source=local_file")
        else:
            await bot.send_message(chat_id=cid, text=caption, parse_mode=ParseMode.HTML,
                                   reply_markup=reply_markup, **kwargs)

        if split_caption:
            await bot.send_message(
                chat_id=cid, text=caption, parse_mode=ParseMode.HTML, **kwargs,
            )

    try:
        await send_once()
        return True, ""
    except Exception as exc:
        error_text = f"{type(exc).__name__}: {exc}"
        if message_thread_id is not None and _thread_error(exc):
            new_id = await _recover_forum_topic(bot, cid, topic_key, message_thread_id)
            if new_id is None:
                logger.error("Forum topic %s is unavailable and could not be recreated", message_thread_id)
                return False, f"forum topic unavailable: {error_text}"
            kwargs["message_thread_id"] = new_id
            try:
                await send_once()
                return True, f"forum topic recreated: {message_thread_id}->{new_id}"
            except Exception as retry_exc:
                error_text = f"{error_text}; recreated topic retry: {type(retry_exc).__name__}: {retry_exc}"
                logger.error("Forum topic retry failed: %s", error_text)
                return False, f"forum topic unavailable: {error_text}"

        logger.warning("Telegram photo send failed; trying text fallback: %s", error_text)
        # If only the photo fails, preserve the actual news as text in the same topic.
        try:
            await bot.send_message(
                chat_id=cid, text=caption, parse_mode=ParseMode.HTML, **kwargs,
            )
            logger.info("Telegram text fallback sent successfully after photo failure")
            return True, f"photo failed but text fallback succeeded: {error_text}"
        except Exception:
            try:
                await bot.send_message(
                    chat_id=cid, text=_plain_text(caption),
                    disable_web_page_preview=False, **kwargs,
                )
                return True, f"HTML/photo failed; plain-text fallback succeeded: {error_text}"
            except Exception as text_error:
                full_error = f"{error_text}; text fallback: {type(text_error).__name__}: {text_error}"
                logger.error("send_photo_text failed: %s", full_error)
                return False, full_error


async def send_two_messages(
    bot: Bot, media, caption1: str, text2: str, chat_id: str = None,
    message_thread_id: int | None = None, topic_key: str | None = None,
) -> bool:
    ok1 = await send_photo_text(bot, media, caption1, chat_id, message_thread_id, topic_key)
    ok2 = await send_text(bot, text2, chat_id, message_thread_id, topic_key)
    return ok1 and ok2


async def notify_admin(bot: Bot, admin_id: str, message: str):
    if not admin_id:
        return
    try:
        await bot.send_message(chat_id=admin_id, text=message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Admin notify error: {e}")


async def update_pinned_message(bot: Bot, text: str, message_id: str | None, chat_id: str = None) -> str | None:
    """Update the pinned market pulse without creating a new post each time."""
    cid = chat_id or _default_chat_id()
    if message_id:
        try:
            await bot.edit_message_text(
                chat_id=cid, message_id=int(message_id), text=text, parse_mode=ParseMode.HTML
            )
            return message_id
        except TelegramError as e:
            logger.warning(f"Не удалось отредактировать закреплённое сообщение, создаю новое: {e}")
    try:
        msg = await bot.send_message(chat_id=cid, text=text, parse_mode=ParseMode.HTML)
        await bot.pin_chat_message(chat_id=cid, message_id=msg.message_id, disable_notification=True)
        return str(msg.message_id)
    except TelegramError as e:
        logger.error(f"Не удалось создать/закрепить сообщение пульса рынка: {e}")
        return None

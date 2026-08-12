import logging
import html
import re
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
from config.config import CHANNEL_ID, GROUP_CHAT_ID


def _default_chat_id() -> str:
    value = GROUP_CHAT_ID or CHANNEL_ID
    return str(value or "").strip().strip('"').strip("'")

logger = logging.getLogger(__name__)


def _plain_text(text: str) -> str:
    """Remove Telegram HTML tags for a last-resort text-only delivery."""
    text = html.unescape(str(text or ""))
    return re.sub(r"<[^>]*>", "", text)


async def send_text(bot: Bot, text: str, chat_id: str = None, message_thread_id: int | None = None) -> bool:
    cid = chat_id or _default_chat_id()
    kwargs = {"message_thread_id": message_thread_id} if message_thread_id is not None else {}
    try:
        await bot.send_message(chat_id=cid, text=text, parse_mode=ParseMode.HTML,
                               disable_web_page_preview=False, **kwargs)
        return True
    except TelegramError as e:
        if message_thread_id is not None and (
            "message thread" in str(e).lower() or "thread not found" in str(e).lower()
        ):
            logger.error(
                "Forum topic %s is unavailable; refusing General fallback",
                message_thread_id,
            )
            return False
        logger.error(f"send_text error: {e}")
        try:
            await bot.send_message(
                chat_id=cid, text=_plain_text(text),
                disable_web_page_preview=False,
                **kwargs,
            )
            return True
        except TelegramError:
            return False

async def send_photo_text(bot: Bot, media, caption: str, chat_id: str = None, message_thread_id: int | None = None) -> bool:
    ok, _ = await send_photo_text_detailed(
        bot, media, caption, chat_id=chat_id, message_thread_id=message_thread_id
    )
    return ok


async def send_photo_text_detailed(
    bot: Bot,
    media,
    caption: str,
    chat_id: str = None,
    message_thread_id: int | None = None,
) -> tuple[bool, str]:
    """Send a photo/caption and return a safe diagnostic on failure.

    A failed photo must not suppress the news post: after photo errors we
    retry as a text message in the same forum topic. Never silently remove
    the thread ID, because that sends the post to General.
    """
    cid = chat_id or _default_chat_id()
    kwargs = {"message_thread_id": message_thread_id} if message_thread_id is not None else {}

    async def send_once(with_thread: bool = True):
        send_kwargs = kwargs if with_thread else {}
        if isinstance(media, bytes):
            await bot.send_photo(chat_id=cid, photo=media, caption=caption,
                                 parse_mode=ParseMode.HTML, **send_kwargs)
        elif isinstance(media, str) and media.startswith("http"):
            await bot.send_photo(chat_id=cid, photo=media, caption=caption,
                                 parse_mode=ParseMode.HTML, **send_kwargs)
        elif isinstance(media, str) and media.endswith((".jpg", ".jpeg", ".png")):
            with open(media, "rb") as f:
                await bot.send_photo(chat_id=cid, photo=f, caption=caption,
                                     parse_mode=ParseMode.HTML, **send_kwargs)
        else:
            await bot.send_message(chat_id=cid, text=caption, parse_mode=ParseMode.HTML,
                                   **send_kwargs)

    try:
        await send_once()
        return True, ""
    except Exception as e:
        error_text = f"{type(e).__name__}: {e}"
        if message_thread_id is not None and (
            "message thread" in str(e).lower() or "thread not found" in str(e).lower()
        ):
            logger.error(
                "Forum topic %s is unavailable; refusing General fallback",
                message_thread_id,
            )
            return False, f"forum topic unavailable: {error_text}"

        # If the photo itself fails, preserve the actual news as text.  This
        # also handles a missing local stub and transient Telegram media errors.
        try:
            await bot.send_message(
                chat_id=cid, text=caption, parse_mode=ParseMode.HTML,
                **(kwargs if message_thread_id is not None else {}),
            )
            return True, f"photo failed but text fallback succeeded: {error_text}"
        except Exception:
            try:
                await bot.send_message(
                    chat_id=cid, text=_plain_text(caption),
                    disable_web_page_preview=False,
                    **kwargs,
                )
                return True, f"HTML/photo failed; plain-text fallback succeeded: {error_text}"
            except Exception as text_error:
                full_error = f"{error_text}; text fallback: {type(text_error).__name__}: {text_error}"
                logger.error("send_photo_text failed: %s", full_error)
                return False, full_error

async def send_two_messages(bot: Bot, media, caption1: str, text2: str, chat_id: str = None, message_thread_id: int | None = None) -> bool:
    ok1 = await send_photo_text(bot, media, caption1, chat_id, message_thread_id)
    ok2 = await send_text(bot, text2, chat_id, message_thread_id)
    return ok1 and ok2

async def notify_admin(bot: Bot, admin_id: str, message: str):
    if not admin_id:
        return
    try:
        await bot.send_message(chat_id=admin_id, text=message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Admin notify error: {e}")


async def update_pinned_message(bot: Bot, text: str, message_id: str | None, chat_id: str = None) -> str | None:
    """Обновляет закреплённое сообщение 'Пульс рынка' на месте, не создавая
    новый пост каждый раз. Если message_id ещё нет или редактирование не
    удалось (сообщение удалено вручную и т.п.) — создаёт новое и закрепляет.
    Возвращает актуальный message_id — вызывающий код должен сохранить его
    (см. modules.storage.set_meta) для следующего обновления."""
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

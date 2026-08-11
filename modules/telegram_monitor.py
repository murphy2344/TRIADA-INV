"""Read-only monitoring of selected Telegram channels through Telethon User API.

TG_SESSION_STRING is a credential. Never log it or commit it. Generate it once
locally with scripts/generate_session.py, then store it as a Render secret.
"""
import logging
import os

from modules import storage

logger = logging.getLogger(__name__)

TG_API_ID = os.environ.get("TG_API_ID", "")
TG_API_HASH = os.environ.get("TG_API_HASH", "")
TG_SESSION_STRING = os.environ.get("TG_SESSION_STRING", "")
WATCHLIST_CHANNELS = [
    item.strip()
    for item in os.environ.get("TG_MONITOR_CHANNELS", "").split(",")
    if item.strip()
]


def is_configured() -> bool:
    return bool(TG_API_ID and TG_API_HASH and TG_SESSION_STRING and WATCHLIST_CHANNELS)


async def fetch_new_messages() -> list[dict]:
    """Return unseen text messages and advance per-channel cursors."""
    if not is_configured():
        logger.info("Telegram monitor disabled: TG_* or TG_MONITOR_CHANNELS is missing")
        return []

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        logger.error("Telegram monitor disabled: telethon is not installed")
        return []

    try:
        api_id = int(TG_API_ID)
    except ValueError:
        logger.error("Telegram monitor disabled: TG_API_ID must be an integer")
        return []

    messages: list[dict] = []
    client = TelegramClient(StringSession(TG_SESSION_STRING), api_id, TG_API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.error("Telegram monitor session is not authorized")
            return []

        for channel in WATCHLIST_CHANNELS:
            cursor_key = f"tg_monitor_last_id:{channel}"
            try:
                last_id = int(await storage.get_meta(cursor_key) or 0)
                entity = await client.get_entity(channel)
                max_seen = last_id
                async for message in client.iter_messages(entity, min_id=last_id, reverse=True):
                    max_seen = max(max_seen, int(message.id))
                    text = (message.message or "").strip()
                    if not text:
                        continue
                    messages.append({
                        "id": f"tg:{channel}:{message.id}",
                        "title": text.splitlines()[0][:240],
                        "summary": text,
                        "text": text,
                        "source": "",
                        "url": "",
                        "channel_name": str(channel),
                        "message_id": int(message.id),
                        "date": message.date.isoformat() if message.date else "",
                    })
                if max_seen > last_id:
                    await storage.set_meta(cursor_key, str(max_seen))
            except Exception:
                logger.exception("Telegram monitor channel failed: %s", channel)
    except Exception:
        logger.exception("Telegram monitor connection failed")
    finally:
        try:
            await client.disconnect()
        except Exception:
            logger.exception("Telegram monitor disconnect failed")

    return messages

"""Read-only monitoring of selected Telegram channels through Telethon User API.

TG_SESSION_STRING is a credential. Never log it or commit it. Generate it once
locally with scripts/generate_session.py, then store it as a Render secret.
"""
import logging
import json
import os

from modules import dedup
from modules import storage

logger = logging.getLogger(__name__)

TG_API_ID = os.environ.get("TG_API_ID", "").strip()
TG_API_HASH = os.environ.get("TG_API_HASH", "").strip()
TG_SESSION_STRING = os.environ.get("TG_SESSION_STRING", "").strip()
ENV_WATCHLIST_CHANNELS = [
    item.strip()
    for item in os.environ.get("TG_MONITOR_CHANNELS", "").split(",")
    if item.strip()
]
CHANNELS_KEY = "triada:tg_monitor_channels"


def normalize_channel(value: str) -> str:
    """Accept @name, t.me/name, or https://t.me/name for public channels."""
    value = (value or "").strip()
    for prefix in ("https://t.me/", "http://t.me/", "t.me/", "telegram.me/"):
        if value.lower().startswith(prefix):
            value = value[len(prefix):]
            break
    value = value.split("?", 1)[0].split("/", 1)[0].strip()
    if value.startswith("@"):
        value = value[1:]
    return value


def _valid_channel(value: str) -> bool:
    return bool(value) and not value.startswith(("+", "joinchat/")) and all(
        char.isalnum() or char == "_" for char in value
    )


async def get_watchlist() -> list[str]:
    """Read the dynamic watchlist, falling back to Render's initial env value."""
    if dedup.USE_REDIS:
        stored = await dedup._redis(["GET", CHANNELS_KEY])
        if stored is not None:
            try:
                channels = json.loads(stored)
                if isinstance(channels, list):
                    return [str(item) for item in channels if str(item)]
            except (TypeError, json.JSONDecodeError):
                logger.warning("Invalid Telegram monitor watchlist in Redis")
    return list(ENV_WATCHLIST_CHANNELS)


async def set_watchlist(channels: list[str]) -> list[str]:
    cleaned = []
    for channel in channels:
        normalized = normalize_channel(channel)
        if _valid_channel(normalized) and normalized not in cleaned:
            cleaned.append(normalized)
    cleaned.sort(key=str.casefold)
    if dedup.USE_REDIS:
        await dedup._redis(["SET", CHANNELS_KEY, json.dumps(cleaned)])
    return cleaned


async def add_channel(value: str) -> tuple[bool, str]:
    normalized = normalize_channel(value)
    if not _valid_channel(normalized):
        return False, "Нужен публичный канал в формате @channel или https://t.me/channel."
    channels = await get_watchlist()
    if normalized.casefold() in {item.casefold() for item in channels}:
        return False, f"Канал @{normalized} уже есть в списке."
    await set_watchlist(channels + [normalized])
    return True, f"Канал @{normalized} добавлен. Проверка выполняется каждые 5 минут."


async def remove_channel(value: str) -> tuple[bool, str]:
    normalized = normalize_channel(value)
    channels = await get_watchlist()
    remaining = [item for item in channels if item.casefold() != normalized.casefold()]
    if len(remaining) == len(channels):
        return False, f"Канала @{normalized} нет в списке."
    await set_watchlist(remaining)
    return True, f"Канал @{normalized} удалён."


async def is_configured() -> bool:
    return bool(TG_API_ID and TG_API_HASH and TG_SESSION_STRING and await get_watchlist())


async def fetch_new_messages() -> list[dict]:
    """Return unseen text messages and advance per-channel cursors."""
    watchlist = await get_watchlist()
    if not TG_API_ID or not TG_API_HASH or not TG_SESSION_STRING or not watchlist:
        logger.info("Telegram monitor disabled: TG_* or the channel watchlist is missing")
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

        for channel in watchlist:
            cursor_key = f"tg_monitor_last_id:{channel}"
            try:
                last_id = int(await storage.get_meta(cursor_key) or 0)
                entity = await client.get_entity(channel)
                # On the first scan, establish a baseline at the newest
                # message. Do not flood the destination with channel history.
                if last_id == 0:
                    latest = await client.get_messages(entity, limit=1)
                    latest_id = int(latest[0].id) if latest else 0
                    if latest_id:
                        await storage.set_meta(cursor_key, str(latest_id))
                    continue
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

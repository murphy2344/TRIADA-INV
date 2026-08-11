"""Forum topics and routing for the Telegram discussion group."""
import asyncio
import logging
import uuid

from telegram.error import TelegramError

from config.config import ADMIN_ID, CHANNEL_ID, GROUP_CHAT_ID
from modules import dedup, storage

logger = logging.getLogger(__name__)

TOPIC_NAMES = {
    "geopolitics": "🌍 Геополитика",
    "companies": "🏢 Компании",
    "markets": "📊 Рынки и макро",
    "crypto": "🪙 Крипта",
    "commodities": "🥇 Сырьё и металлы",
}

_TOPIC_IDS: dict[str, int] = {}
REDIS_TOPIC_PREFIX = "triada:forum_topic"


def target_chat_id() -> str:
    """Use the forum group when configured; keep CHANNEL_ID as a safe fallback."""
    return GROUP_CHAT_ID or CHANNEL_ID


def route_topic(analysis: dict) -> str:
    """Map an AI analysis to one of the configured forum topics."""
    asset_class = analysis.get("asset_class", "none")
    if asset_class == "crypto":
        return "crypto"
    if asset_class == "commodity":
        return "commodities"

    category = analysis.get("category", "market_move")
    if category == "geopolitics":
        return "geopolitics"
    if category == "company":
        return "companies"
    return "markets"


def set_topic_ids(topic_ids: dict[str, int] | None) -> None:
    _TOPIC_IDS.clear()
    if topic_ids:
        _TOPIC_IDS.update(topic_ids)


def get_topic_id(topic_key: str) -> int | None:
    value = _TOPIC_IDS.get(topic_key)
    return int(value) if value is not None else None


async def ensure_topics_exist(bot, group_chat_id) -> dict[str, int]:
    """Load topic IDs and create only genuinely missing forum topics.

    Render may briefly run two processes during a deploy. A Redis NX lock
    prevents both processes from seeing missing IDs and creating duplicates.
    """
    if not group_chat_id:
        logger.info("GROUP_CHAT_ID is not configured; forum topics are disabled")
        set_topic_ids({})
        return {}

    async def load_saved() -> dict[str, int]:
        saved_ids: dict[str, int] = {}
        for key in TOPIC_NAMES:
            redis_key = f"{REDIS_TOPIC_PREFIX}:{group_chat_id}:{key}"
            meta_key = f"topic_id:{group_chat_id}:{key}"
            saved = await dedup._redis(["GET", redis_key]) if dedup.USE_REDIS else None
            if not saved:
                saved = await storage.get_meta(meta_key)
            if saved:
                try:
                    saved_ids[key] = int(saved)
                except (TypeError, ValueError):
                    logger.warning("Invalid saved topic id for %s; it will be recreated", key)
        return saved_ids

    result = await load_saved()
    if len(result) == len(TOPIC_NAMES):
        set_topic_ids(result)
        logger.info("Forum topics loaded from persistent storage: %s", result)
        return result

    lock_name = f"forum_topics:{group_chat_id}"
    lock_owner = uuid.uuid4().hex
    locked = False
    if dedup.USE_REDIS:
        for _ in range(60):
            locked = await dedup.acquire_lock(lock_name, lock_owner, ttl=120)
            if locked:
                break
            result = await load_saved()
            if len(result) == len(TOPIC_NAMES):
                set_topic_ids(result)
                logger.info("Forum topics initialized by another process: %s", result)
                return result
            await asyncio.sleep(2)
        if not locked:
            logger.error("Could not acquire forum topic lock; refusing to create duplicates")
            set_topic_ids(result)
            return result
    else:
        logger.warning(
            "Redis is unavailable; forum topic creation cannot be coordinated across "
            "overlapping Render processes"
        )

    try:
        # Reload after locking because another process may have created some
        # topics while this process was waiting.
        result = await load_saved()
        for key, name in TOPIC_NAMES.items():
            if key in result:
                continue

            redis_key = f"{REDIS_TOPIC_PREFIX}:{group_chat_id}:{key}"
            meta_key = f"topic_id:{group_chat_id}:{key}"
            try:
                topic = await bot.create_forum_topic(chat_id=group_chat_id, name=name)
                thread_id = int(topic.message_thread_id)
                await storage.set_meta(meta_key, str(thread_id))
                if dedup.USE_REDIS:
                    await dedup._redis(["SET", redis_key, str(thread_id)])
                result[key] = thread_id
                logger.info("Forum topic ready: %s=%s", key, thread_id)
            except TelegramError as exc:
                logger.error("Could not create forum topic %s: %s", key, exc)
                if ADMIN_ID:
                    try:
                        await bot.send_message(
                            chat_id=ADMIN_ID,
                            text=(
                                "❌ Не удалось создать тему форума "
                                f"«{name}». Проверьте, что GROUP_CHAT_ID — это супергруппа, "
                                "в ней включены «Темы», а бот имеет право «Управление темами»."
                            ),
                        )
                    except Exception:
                        logger.exception("Could not notify admin about forum topic failure")
            except Exception:
                logger.exception("Unexpected forum topic error for %s", key)
    finally:
        if locked:
            await dedup.release_lock(lock_name, lock_owner)

    set_topic_ids(result)
    return result
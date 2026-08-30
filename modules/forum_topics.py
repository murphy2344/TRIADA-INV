"""Managed forum topics with persistent IDs and self-healing after deletion.

Telegram's built-in General thread is intentionally not managed here.  It is
the fallback destination for categories that do not have a dedicated topic.
"""
import asyncio
import json
import logging
import os
import uuid

from telegram.error import TelegramError

from config.config import ADMIN_ID, CHANNEL_ID, GROUP_CHAT_ID
from modules import dedup, storage

logger = logging.getLogger(__name__)

TOPIC_NAMES = {
    "geopolitics": "🌍 GEO",
    "companies": "🏢 COMPANIES",
    "markets": "📊 MARKETS",
    "crypto": "🪙 CRYPTO",
    "commodities": "🥇 COMMODITIES",
}
GENERAL_TOPIC_KEY = "general"

_TOPIC_IDS: dict[str, int] = {}
_LOCAL_TOPIC_LOCK = asyncio.Lock()
REDIS_TOPIC_PREFIX = "triada:forum_topic"
TOPIC_MAP_PREFIX = "triada:forum_topics"


def normalize_group_chat_id(group_chat_id) -> str:
    return str(group_chat_id or "").strip().strip('"').strip("'")


def target_chat_id() -> str:
    return normalize_group_chat_id(GROUP_CHAT_ID) or normalize_group_chat_id(CHANNEL_ID)


def route_topic(analysis: dict) -> str:
    asset_class = analysis.get("asset_class", "none")
    if asset_class == "crypto":
        return "crypto"
    if asset_class == "commodity":
        return "commodities"
    category = analysis.get("ai_category") or analysis.get("category", "market_move")
    if category in {"geopolitics", "regulatory", "central_bank"}:
        return "geopolitics"
    if category in {"company", "corporate", "earnings"}:
        return "companies"
    if category in {"macro", "market_move", "bonds", "commodity"}:
        return "markets"
    return "general"


def set_topic_ids(topic_ids: dict[str, int] | None) -> None:
    _TOPIC_IDS.clear()
    if topic_ids:
        _TOPIC_IDS.update(topic_ids)


def get_topic_id(topic_key: str) -> int | None:
    # General is Telegram's built-in forum thread. Never use a stored ID for
    # it and never pass message_thread_id so Telegram routes there naturally.
    if topic_key == GENERAL_TOPIC_KEY:
        return None
    value = _TOPIC_IDS.get(topic_key)
    return int(value) if value is not None else None


def _thread_missing(exc: Exception) -> bool:
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


async def _redis_get(key: str):
    if not dedup.USE_REDIS:
        return None
    return await dedup._redis(["GET", key])


async def _load_saved(group_chat_id: str) -> dict[str, int]:
    saved_ids: dict[str, int] = {}
    configured = os.environ.get("FORUM_TOPIC_IDS", "").strip()
    if configured:
        try:
            parsed = json.loads(configured)
            for key, value in parsed.items():
                if key in TOPIC_NAMES:
                    saved_ids[key] = int(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.error("FORUM_TOPIC_IDS is not valid JSON")

    aggregate = await _redis_get(f"{TOPIC_MAP_PREFIX}:{group_chat_id}")
    if aggregate:
        try:
            parsed = json.loads(aggregate)
            for key, value in parsed.items():
                if key in TOPIC_NAMES:
                    saved_ids[key] = int(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning("Invalid aggregate forum topic map in Redis")

    for key in TOPIC_NAMES:
        if key in saved_ids:
            continue
        redis_key = f"{REDIS_TOPIC_PREFIX}:{group_chat_id}:{key}"
        meta_key = f"topic_id:{group_chat_id}:{key}"
        saved = await _redis_get(redis_key)
        if not saved:
            saved = await storage.get_meta(meta_key)
        if saved:
            try:
                saved_ids[key] = int(saved)
            except (TypeError, ValueError):
                logger.warning("Invalid saved topic ID for %s; it will be recreated", key)
    return saved_ids


async def _save_topic_map(group_chat_id: str, topic_ids: dict[str, int]) -> None:
    if dedup.USE_REDIS:
        await dedup._redis([
            "SET",
            f"{TOPIC_MAP_PREFIX}:{group_chat_id}",
            json.dumps(topic_ids, separators=(",", ":")),
        ])


async def _save_topic_id(group_chat_id: str, key: str, thread_id: int) -> None:
    redis_key = f"{REDIS_TOPIC_PREFIX}:{group_chat_id}:{key}"
    meta_key = f"topic_id:{group_chat_id}:{key}"
    await storage.set_meta(meta_key, str(thread_id))
    if dedup.USE_REDIS:
        await dedup._redis(["SET", redis_key, str(thread_id)])


async def _clear_topic_id(group_chat_id: str, key: str) -> None:
    redis_key = f"{REDIS_TOPIC_PREFIX}:{group_chat_id}:{key}"
    meta_key = f"topic_id:{group_chat_id}:{key}"
    # Empty SQLite metadata is treated as absent by _load_saved and is safe
    # for older storage versions that do not have delete_meta().
    await storage.set_meta(meta_key, "")
    if dedup.USE_REDIS:
        await dedup._redis(["DEL", redis_key])


async def _probe_topic(bot, group_chat_id: str, thread_id: int) -> bool:
    """Check a thread because Telegram Bot API has no list-forum-topics method.

    The probe is silent and deleted immediately. It is only run at startup, not
    for every post. A deleted topic produces Message thread not found.
    """
    probe = None
    try:
        probe = await bot.send_message(
            chat_id=group_chat_id,
            message_thread_id=thread_id,
            text="⁣",
            disable_notification=True,
        )
        if probe:
            try:
                await bot.delete_message(group_chat_id, probe.message_id)
            except Exception as exc:
                logger.warning("Could not delete forum validation probe: %s", exc)
        return True
    except TelegramError as exc:
        if _thread_missing(exc):
            return False
        # Permission/network errors are not proof that the topic was deleted.
        logger.warning("Could not validate forum topic %s: %s", thread_id, exc)
        return True
    except Exception as exc:
        logger.warning("Unexpected forum topic validation error: %s", exc)
        return True


async def _notify_admin_topic_error(bot, name: str) -> None:
    if not ADMIN_ID:
        return
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


async def _create_missing_topics(bot, group_chat_id: str, result: dict[str, int]) -> dict[str, int]:
    for key, name in TOPIC_NAMES.items():
        if key in result:
            continue
        try:
            topic = await bot.create_forum_topic(chat_id=group_chat_id, name=name)
            thread_id = int(topic.message_thread_id)
            await _save_topic_id(group_chat_id, key, thread_id)
            result[key] = thread_id
            await _save_topic_map(group_chat_id, result)
            logger.info("Forum topic ready: %s=%s", key, thread_id)
        except TelegramError as exc:
            logger.error("Could not create forum topic %s: %s", key, exc)
            await _notify_admin_topic_error(bot, name)
        except Exception:
            logger.exception("Unexpected forum topic error for %s", key)
    return result


async def ensure_topics_exist(bot, group_chat_id) -> dict[str, int]:
    """Validate saved IDs, recreate deleted topics, and persist IDs once.

    Telegram does not expose a getForumTopics method. Therefore a startup
    validation sends one silent zero-width probe per saved topic and deletes it
    immediately. Normal restarts reuse the same IDs; deleted topics are
    detected and recreated instead of causing Message thread not found errors.
    """
    group_chat_id = normalize_group_chat_id(group_chat_id)
    if not group_chat_id:
        logger.info("GROUP_CHAT_ID is not configured; forum topics are disabled")
        set_topic_ids({})
        return {}

    lock_name = f"forum_topics:{group_chat_id}"
    lock_owner = uuid.uuid4().hex
    redis_locked = False

    if dedup.USE_REDIS:
        for _ in range(60):
            if await dedup.acquire_lock(lock_name, lock_owner, ttl=120):
                redis_locked = True
                break
            await asyncio.sleep(2)
        if not redis_locked:
            result = await _load_saved(group_chat_id)
            logger.error("Could not acquire forum topic lock; using saved IDs without creating duplicates")
            set_topic_ids(result)
            return result

    async with _LOCAL_TOPIC_LOCK:
        try:
            result = await _load_saved(group_chat_id)
            invalid = []
            for key, thread_id in list(result.items()):
                if not await _probe_topic(bot, group_chat_id, thread_id):
                    invalid.append(key)
                    logger.warning(
                        "Saved forum topic is gone: %s=%s; recreating it", key, thread_id
                    )
            for key in invalid:
                result.pop(key, None)
                await _clear_topic_id(group_chat_id, key)

            result = await _create_missing_topics(bot, group_chat_id, result)
            if len(result) == len(TOPIC_NAMES):
                await _save_topic_map(group_chat_id, result)
            set_topic_ids(result)
            logger.info("Forum topics initialized: %s", result)
            return result
        finally:
            if redis_locked:
                await dedup.release_lock(lock_name, lock_owner)


async def recreate_topic(bot, group_chat_id, topic_key: str, stale_thread_id: int | None = None) -> int | None:
    """Create one replacement topic after a topic is deleted while running."""
    group_chat_id = normalize_group_chat_id(group_chat_id)
    if not group_chat_id or topic_key not in TOPIC_NAMES:
        return None

    lock_name = f"forum_topics:{group_chat_id}"
    lock_owner = uuid.uuid4().hex
    redis_locked = False
    if dedup.USE_REDIS:
        for _ in range(60):
            if await dedup.acquire_lock(lock_name, lock_owner, ttl=120):
                redis_locked = True
                break
            current = await _load_saved(group_chat_id)
            current_id = current.get(topic_key)
            if current_id and current_id != stale_thread_id:
                set_topic_ids(current)
                return current_id
            await asyncio.sleep(2)
        if not redis_locked:
            return None

    async with _LOCAL_TOPIC_LOCK:
        try:
            current = await _load_saved(group_chat_id)
            current_id = current.get(topic_key)
            if current_id and current_id != stale_thread_id:
                set_topic_ids(current)
                return current_id
            try:
                topic = await bot.create_forum_topic(
                    chat_id=group_chat_id, name=TOPIC_NAMES[topic_key]
                )
                new_id = int(topic.message_thread_id)
                current[topic_key] = new_id
                await _save_topic_id(group_chat_id, topic_key, new_id)
                await _save_topic_map(group_chat_id, current)
                set_topic_ids(current)
                logger.warning("Forum topic recreated: %s=%s", topic_key, new_id)
                return new_id
            except TelegramError as exc:
                logger.error("Could not recreate forum topic %s: %s", topic_key, exc)
                await _notify_admin_topic_error(bot, TOPIC_NAMES[topic_key])
                return None
        finally:
            if redis_locked:
                await dedup.release_lock(lock_name, lock_owner)

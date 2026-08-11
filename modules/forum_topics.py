"""Forum topics and routing for the Telegram discussion group."""
import logging

from telegram.error import TelegramError

from config.config import ADMIN_ID, CHANNEL_ID, GROUP_CHAT_ID
from modules import storage

logger = logging.getLogger(__name__)

TOPIC_NAMES = {
    "geopolitics": "🌍 Геополитика",
    "companies": "🏢 Компании",
    "markets": "📊 Рынки и макро",
    "crypto": "🪙 Крипта",
    "commodities": "🥇 Сырьё и металлы",
}

_TOPIC_IDS: dict[str, int] = {}


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
    """Load topic IDs from bot_meta and create missing forum topics once."""
    if not group_chat_id:
        logger.info("GROUP_CHAT_ID is not configured; forum topics are disabled")
        set_topic_ids({})
        return {}

    result: dict[str, int] = {}
    for key, name in TOPIC_NAMES.items():
        meta_key = f"topic_id:{key}"
        saved = await storage.get_meta(meta_key)
        if saved:
            try:
                result[key] = int(saved)
                continue
            except ValueError:
                logger.warning("Invalid saved topic id for %s; recreating", key)

        try:
            topic = await bot.create_forum_topic(chat_id=group_chat_id, name=name)
            thread_id = int(topic.message_thread_id)
            await storage.set_meta(meta_key, str(thread_id))
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
        except Exception as exc:
            logger.exception("Unexpected forum topic error for %s: %s", key, exc)

    set_topic_ids(result)
    return result

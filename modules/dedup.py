import re
import os
import json
import logging
import hashlib
import aiohttp
from modules.storage import is_published, get_recent_titles, mark_published as sqlite_mark

logger = logging.getLogger(__name__)

UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "").rstrip("/")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
USE_REDIS = bool(UPSTASH_URL and UPSTASH_TOKEN)
PREFIX = "triada"
TTL = 21600  # 6 hours


if not USE_REDIS:
    logger.warning("UPSTASH_REDIS_REST_URL/TOKEN not set — using SQLite dedup (not persistent across restarts)")


async def _redis(cmd: list):
    """Execute a single Upstash Redis REST command."""
    headers = {
        "Authorization": f"Bearer {UPSTASH_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                UPSTASH_URL, data=json.dumps(cmd), headers=headers,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as r:
                data = await r.json()
                return data.get("result")
    except Exception as e:
        logger.error(f"Upstash Redis error {cmd[0]}: {e}")
        return None


def _extract_keywords(text: str) -> set:
    text = text.lower()
    words = re.findall(r'\b[a-zа-яё]{4,}\b', text)
    stopwords = {
        "that", "this", "with", "from", "they", "have", "will", "been",
        "were", "what", "when", "which", "than", "then", "also", "more",
        "после", "перед", "через", "этого", "этот", "этом", "также",
    }
    return set(w for w in words if w not in stopwords)


def _similarity(title1: str, title2: str) -> float:
    kw1 = _extract_keywords(title1)
    kw2 = _extract_keywords(title2)
    if not kw1 or not kw2:
        return 0.0
    return len(kw1 & kw2) / len(kw1 | kw2)


# ── Redis helpers ─────────────────────────────────────────────────────────────

async def _redis_is_published(news_id: str) -> bool:
    result = await _redis(["GET", f"{PREFIX}:pub:{news_id}"])
    return result is not None


async def _redis_get_recent_titles() -> list[str]:
    result = await _redis(["LRANGE", f"{PREFIX}:titles", "0", "499"])
    return result if isinstance(result, list) else []


async def _redis_mark(news_id: str, title: str):
    await _redis(["SET", f"{PREFIX}:pub:{news_id}", "1", "EX", str(TTL)])
    await _redis(["LPUSH", f"{PREFIX}:titles", title])
    await _redis(["LTRIM", f"{PREFIX}:titles", "0", "499"])
    await _redis(["EXPIRE", f"{PREFIX}:titles", "86400"])


# ── Public interface ───────────────────────────────────────────────────────────

async def is_duplicate(news_id: str, title: str, threshold: float = 0.6) -> bool:
    # Check exact ID match
    if USE_REDIS:
        if await _redis_is_published(news_id):
            return True
        recent = await _redis_get_recent_titles()
    else:
        if await is_published(news_id):
            return True
        recent = await get_recent_titles(hours=6)

    # Jaccard similarity check
    for recent_title in recent:
        if _similarity(title, recent_title) >= threshold:
            logger.info(f"Duplicate: '{title[:50]}' ~ '{recent_title[:50]}'")
            return True
    return False


def _event_fingerprint(subject_en: str, category: str) -> str:
    """Ключ события, НЕ зависящий от текста/языка заголовка. Разные
    источники дают разный news_id и сильно разный текст заголовка (иногда
    на разных языках) для ОДНОГО И ТОГО ЖЕ события — Jaccard по словам это
    не ловит. Здесь сравниваем по теме (subject_en) + категории."""
    key = (subject_en or "").strip().lower()
    key = re.sub(r"[^a-z0-9 ]", "", key)
    key = re.sub(r"\s+", " ", key).strip()
    return f"{category}:{key}"


async def is_duplicate_event(subject_en: str, category: str) -> bool:
    """Вызывать ПОСЛЕ AI-анализа, когда уже известны subject_en/category.
    Это вторая, более надёжная проверка — ловит дубли независимо от
    формулировки и языка исходного заголовка."""
    fingerprint = _event_fingerprint(subject_en, category)
    if fingerprint.endswith(":") or not fingerprint.split(":", 1)[1]:
        return False  # пустой subject_en — нечего сравнивать

    if USE_REDIS:
        result = await _redis(["GET", f"{PREFIX}:event:{fingerprint}"])
        return result is not None
    else:
        # SQLite fallback: используем ту же таблицу через title-подобное
        # сравнение — храним fingerprint как обычный "заголовок"
        recent = await get_recent_titles(hours=6)
        return fingerprint in recent


async def mark_event_published(subject_en: str, category: str):
    fingerprint = _event_fingerprint(subject_en, category)
    if fingerprint.endswith(":") or not fingerprint.split(":", 1)[1]:
        return
    if USE_REDIS:
        await _redis(["SET", f"{PREFIX}:event:{fingerprint}", "1", "EX", str(TTL)])
    else:
        # SQLite fallback: сохраняем fingerprint как обычную запись с
        # синтетическим news_id, чтобы get_recent_titles() его тоже видел
        # при следующей проверке is_duplicate_event()
        import hashlib
        from modules.storage import mark_published
        synthetic_id = hashlib.md5(fingerprint.encode()).hexdigest()
        await mark_published(synthetic_id, fingerprint, "event_fingerprint", "", "EVENT")


async def mark_as_published(news_id: str, title: str):
    """Call this after successful post to register in dedup store."""
    if USE_REDIS:
        await _redis_mark(news_id, title)
    # Always also mark in SQLite as secondary record
    # (storage.mark_published is called from pipeline separately)


async def check_redis_connection() -> tuple[bool, str]:
    """Проверяет соединение с Upstash Redis через PING.
    Возвращает (True, "") если OK, (False, причина) если ошибка."""
    if not USE_REDIS:
        return False, "переменные UPSTASH_REDIS_REST_URL / TOKEN не заданы"
    try:
        headers = {
            "Authorization": f"Bearer {UPSTASH_TOKEN}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                UPSTASH_URL,
                data=json.dumps(["PING"]),
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                status = r.status
                raw = await r.text()
                logger.info(f"Redis PING → HTTP {status}: {raw[:200]}")
                if status == 401:
                    return False, f"HTTP 401 — неверный токен (UPSTASH_REDIS_REST_TOKEN)"
                if status == 404:
                    return False, f"HTTP 404 — неверный URL базы данных (UPSTASH_REDIS_REST_URL)"
                if status != 200:
                    return False, f"HTTP {status}: {raw[:120]}"
                import json as _json
                data = _json.loads(raw)
                result = data.get("result")
                if result == "PONG":
                    return True, ""
                return False, f"неожиданный ответ: {raw[:120]}"
    except aiohttp.ClientConnectorError as e:
        return False, f"нет соединения с хостом: {e}"
    except asyncio.TimeoutError:
        return False, "таймаут 8с — хост не отвечает"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

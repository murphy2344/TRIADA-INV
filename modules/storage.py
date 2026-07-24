import aiosqlite
import logging
from config.config import DB_PATH
import os

logger = logging.getLogger(__name__)

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS published_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_id TEXT UNIQUE,
                title TEXT,
                source TEXT,
                url TEXT,
                published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                post_type TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE,
                posts_count INTEGER DEFAULT 0,
                errors_count INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                subject TEXT,
                recommendation TEXT,
                price_at_post REAL,
                posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                checked INTEGER DEFAULT 0,
                correct INTEGER,
                price_after REAL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.commit()
    logger.info("Database initialized")

async def is_published(news_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM published_news WHERE news_id = ?", (news_id,)
        ) as cursor:
            return await cursor.fetchone() is not None

async def mark_published(news_id: str, title: str, source: str, url: str, post_type: str):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT OR IGNORE INTO published_news (news_id, title, source, url, post_type) VALUES (?, ?, ?, ?, ?)",
                (news_id, title, source, url, post_type)
            )
            await db.commit()
        except Exception as e:
            logger.error(f"DB mark_published error: {e}")

async def get_recent_titles(hours: int = 6) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT title FROM published_news WHERE published_at > datetime('now', ? || ' hours')",
            (f"-{hours}",)
        ) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

async def increment_stats():
    from datetime import date
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO bot_stats (date, posts_count) VALUES (?, 1) "
                "ON CONFLICT(date) DO UPDATE SET posts_count = posts_count + 1",
                (today,)
            )
            await db.commit()
        except Exception as e:
            logger.error(f"DB increment_stats error: {e}")

async def get_today_stats() -> dict:
    from datetime import date
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT posts_count, errors_count FROM bot_stats WHERE date = ?", (today,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"posts": row[0], "errors": row[1]}
            return {"posts": 0, "errors": 0}


async def save_recommendation(ticker: str, subject: str, recommendation: str, price_at_post: float):
    """Сохраняет рекомендацию с ценой на момент публикации — для последующей
    проверки трек-рекорда через 24 часа. Вызывается только когда есть тикер
    и рекомендация не 'neutral' (для neutral нет чёткого направления, которое
    можно проверить)."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO recommendations (ticker, subject, recommendation, price_at_post) "
                "VALUES (?, ?, ?, ?)",
                (ticker, subject, recommendation, price_at_post),
            )
            await db.commit()
        except Exception as e:
            logger.error(f"DB save_recommendation error: {e}")


async def get_unchecked_recommendations(older_than_hours: int = 24) -> list:
    """Рекомендации старше N часов, ещё не проверенные — готовы к сверке цены."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, ticker, recommendation, price_at_post FROM recommendations "
            "WHERE checked = 0 AND posted_at <= datetime('now', ? || ' hours')",
            (f"-{older_than_hours}",),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {"id": r[0], "ticker": r[1], "recommendation": r[2], "price_at_post": r[3]}
                for r in rows
            ]


async def update_recommendation_result(rec_id: int, price_after: float, correct: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "UPDATE recommendations SET checked = 1, correct = ?, price_after = ? WHERE id = ?",
                (1 if correct else 0, price_after, rec_id),
            )
            await db.commit()
        except Exception as e:
            logger.error(f"DB update_recommendation_result error: {e}")


async def get_accuracy_stats(days: int = 7) -> dict:
    """% попаданий рекомендаций за последние N дней — для weekly recap и /status."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*), SUM(correct) FROM recommendations "
            "WHERE checked = 1 AND posted_at >= datetime('now', ? || ' days')",
            (f"-{days}",),
        ) as cursor:
            row = await cursor.fetchone()
            total = row[0] or 0
            correct = row[1] or 0
            accuracy = round(correct / total * 100) if total else None
            return {"total": total, "correct": correct, "accuracy_pct": accuracy}


async def get_meta(key: str) -> str | None:
    """Универсальное key-value хранилище для мелких значений (например,
    ID закреплённого сообщения с пульсом рынка)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM bot_meta WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def set_meta(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO bot_meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await db.commit()


async def was_alerted_recently(ticker: str, signal_type: str, cooldown_hours: int = 24) -> bool:
    """Проверка антиспама: не повторять один и тот же технический сигнал
    по тому же тикеру чаще, чем раз в cooldown_hours."""
    key = f"ta_alert:{ticker}:{signal_type}"
    value = await get_meta(key)
    return value is not None  # bot_meta не хранит TTL сам по себе — см. ниже


async def mark_alerted(ticker: str, signal_type: str):
    key = f"ta_alert:{ticker}:{signal_type}"
    import datetime
    await set_meta(key, datetime.datetime.utcnow().isoformat())


async def clear_stale_alerts(cooldown_hours: int = 24):
    """Чистит записи об алертах старше cooldown_hours — вызывать периодически,
    иначе was_alerted_recently будет молчать вечно (bot_meta без TTL)."""
    import datetime
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=cooldown_hours)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT key, value FROM bot_meta WHERE key LIKE 'ta_alert:%'"
        ) as cursor:
            rows = await cursor.fetchall()
        for key, value in rows:
            try:
                ts = datetime.datetime.fromisoformat(value)
                if ts < cutoff:
                    await db.execute("DELETE FROM bot_meta WHERE key = ?", (key,))
            except Exception:
                continue
        await db.commit()

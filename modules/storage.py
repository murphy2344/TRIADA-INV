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
                price_after REAL,
                signal_id TEXT,
                entry_time TIMESTAMP,
                category TEXT DEFAULT 'market_move',
                confidence REAL,
                source TEXT,
                horizon_hours INTEGER DEFAULT 24,
                pnl_percent REAL,
                max_drawdown_percent REAL,
                direction_correct INTEGER
            )
        """)
        async with db.execute("PRAGMA table_info(recommendations)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        migrations = {
            "signal_id": "TEXT",
            "entry_time": "TIMESTAMP",
            "category": "TEXT DEFAULT 'market_move'",
            "confidence": "REAL",
            "source": "TEXT",
            "horizon_hours": "INTEGER DEFAULT 24",
            "pnl_percent": "REAL",
            "max_drawdown_percent": "REAL",
            "direction_correct": "INTEGER",
        }
        for column, definition in migrations.items():
            if column not in columns:
                await db.execute(
                    f"ALTER TABLE recommendations ADD COLUMN {column} {definition}"
                )
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # User portfolios
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_portfolios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                ticker TEXT,
                quantity REAL,
                avg_price REAL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, ticker)
            )
        """)
        # User price alerts
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                ticker TEXT,
                target_price REAL,
                direction TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                triggered INTEGER DEFAULT 0
            )
        """)
        # User watchlists
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_watchlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                ticker TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, ticker)
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


async def save_recommendation(
    ticker: str,
    subject: str,
    recommendation: str,
    price_at_post: float,
    category: str = "market_move",
    confidence: float | None = None,
    source: str = "",
):
    """Сохраняет рекомендацию с ценой на момент публикации — для последующей
    проверки трек-рекорда через 24 часа. Вызывается только когда есть тикер
    и рекомендация не 'neutral' (для neutral нет чёткого направления, которое
    можно проверить)."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            from datetime import datetime, timezone
            from modules.track_record import horizon_for
            now = datetime.now(timezone.utc)
            await db.execute(
                "INSERT INTO recommendations "
                "(ticker, subject, recommendation, price_at_post, signal_id, entry_time, "
                "category, confidence, source, horizon_hours) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ticker, subject, recommendation, price_at_post,
                    f"{ticker}:{now.isoformat()}", now.isoformat(), category,
                    confidence, source, horizon_for(category),
                ),
            )
            await db.commit()
        except Exception as e:
            logger.error(f"DB save_recommendation error: {e}")


async def get_unchecked_recommendations(older_than_hours: int | None = None) -> list:
    """Return unchecked signals whose configured horizon has elapsed."""
    async with aiosqlite.connect(DB_PATH) as db:
        if older_than_hours is None:
            query = (
                "SELECT id, ticker, recommendation, price_at_post, category, confidence, "
                "source, horizon_hours, posted_at FROM recommendations "
                "WHERE checked = 0 AND datetime('now') >= "
                "datetime(posted_at, '+' || COALESCE(horizon_hours, 24) || ' hours')"
            )
            params = ()
        else:
            query = (
                "SELECT id, ticker, recommendation, price_at_post, category, confidence, "
                "source, horizon_hours, posted_at FROM recommendations "
                "WHERE checked = 0 AND posted_at <= datetime('now', ? || ' hours')"
            )
            params = (f"-{older_than_hours}",)
        async with db.execute(
            query, params,
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": r[0], "ticker": r[1], "recommendation": r[2],
                    "price_at_post": r[3], "category": r[4] or "market_move",
                    "confidence": r[5], "source": r[6] or "",
                    "horizon_hours": r[7] or 24, "posted_at": r[8],
                }
                for r in rows
            ]


async def update_recommendation_result(
    rec_id: int,
    price_after: float,
    correct: bool,
    pnl_percent: float | None = None,
    max_drawdown_percent: float | None = None,
):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "UPDATE recommendations SET checked = 1, correct = ?, "
                "direction_correct = ?, price_after = ?, pnl_percent = ?, "
                "max_drawdown_percent = ? WHERE id = ?",
                (
                    1 if correct else 0, 1 if correct else 0, price_after,
                    pnl_percent, max_drawdown_percent, rec_id,
                ),
            )
            await db.commit()
        except Exception as e:
            logger.error(f"DB update_recommendation_result error: {e}")


async def get_accuracy_stats(days: int = 7) -> dict:
    """% попаданий рекомендаций за последние N дней — для weekly recap и /status."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*), SUM(correct), AVG(pnl_percent) FROM recommendations "
            "WHERE checked = 1 AND posted_at >= datetime('now', ? || ' days')",
            (f"-{days}",),
        ) as cursor:
            row = await cursor.fetchone()
            total = row[0] or 0
            correct = row[1] or 0
            accuracy = round(correct / total * 100) if total else None
            return {
                "total": total,
                "correct": correct,
                "accuracy_pct": accuracy,
                "avg_pnl": round(row[2], 2) if row[2] is not None else 0.0,
            }


async def get_track_record_by_category(days: int = 7) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT category, COUNT(*), SUM(correct), AVG(pnl_percent) "
            "FROM recommendations WHERE checked = 1 "
            "AND posted_at >= datetime('now', ? || ' days') GROUP BY category",
            (f"-{days}",),
        ) as cursor:
            rows = await cursor.fetchall()
    result = []
    for category, count, correct, avg_pnl in rows:
        result.append({
            "category": category or "market_move",
            "count": count,
            "correct": correct or 0,
            "accuracy_pct": round((correct or 0) / count * 100) if count else 0,
            "avg_pnl": round(avg_pnl, 2) if avg_pnl is not None else 0.0,
        })
    return result


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


# ─── User Portfolio Functions ────────────────────────────────────────────────

async def add_to_portfolio(user_id: int, ticker: str, quantity: float, avg_price: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO user_portfolios (user_id, ticker, quantity, avg_price)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, ticker) DO UPDATE SET
               quantity = quantity + excluded.quantity,
               avg_price = ((user_portfolios.quantity * user_portfolios.avg_price +
                            excluded.quantity * excluded.avg_price) /
                           (user_portfolios.quantity + excluded.quantity))""",
            (user_id, ticker.upper(), quantity, avg_price)
        )
        await db.commit()


async def remove_from_portfolio(user_id: int, ticker: str, quantity: float = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if quantity is None:
            await db.execute(
                "DELETE FROM user_portfolios WHERE user_id = ? AND ticker = ?",
                (user_id, ticker.upper())
            )
        else:
            await db.execute(
                """UPDATE user_portfolios SET quantity = quantity - ?
                   WHERE user_id = ? AND ticker = ?""",
                (quantity, user_id, ticker.upper())
            )
            await db.execute(
                "DELETE FROM user_portfolios WHERE user_id = ? AND quantity <= 0",
                (user_id,)
            )
        await db.commit()


async def get_portfolio(user_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT ticker, quantity, avg_price FROM user_portfolios WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"ticker": r[0], "quantity": r[1], "avg_price": r[2]} for r in rows]


# ─── User Alerts Functions ───────────────────────────────────────────────────

async def add_alert(user_id: int, ticker: str, target_price: float, direction: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO user_alerts (user_id, ticker, target_price, direction)
               VALUES (?, ?, ?, ?)""",
            (user_id, ticker.upper(), target_price, direction)
        )
        await db.commit()


async def get_user_alerts(user_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT id, ticker, target_price, direction FROM user_alerts
               WHERE user_id = ? AND triggered = 0""",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"id": r[0], "ticker": r[1], "target_price": r[2], "direction": r[3]} for r in rows]


async def get_all_active_alerts() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, user_id, ticker, target_price, direction FROM user_alerts WHERE triggered = 0"
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"id": r[0], "user_id": r[1], "ticker": r[2], "target_price": r[3], "direction": r[4]} for r in rows]


async def mark_alert_triggered(alert_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE user_alerts SET triggered = 1 WHERE id = ?",
            (alert_id,)
        )
        await db.commit()


async def delete_alert(user_id: int, alert_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM user_alerts WHERE id = ? AND user_id = ?",
            (alert_id, user_id)
        )
        await db.commit()


# ─── User Watchlist Functions ────────────────────────────────────────────────

async def add_to_watchlist(user_id: int, ticker: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_watchlists (user_id, ticker) VALUES (?, ?)",
            (user_id, ticker.upper())
        )
        await db.commit()


async def remove_from_watchlist(user_id: int, ticker: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM user_watchlists WHERE user_id = ? AND ticker = ?",
            (user_id, ticker.upper())
        )
        await db.commit()


async def get_watchlist(user_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT ticker FROM user_watchlists WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

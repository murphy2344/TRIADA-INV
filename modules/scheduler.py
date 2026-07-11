import logging
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from modules import pipeline

logger = logging.getLogger(__name__)
MSK = pytz.timezone("Europe/Moscow")


def build_scheduler(bot, admin_id: str) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=MSK)

    # Breaking news — every 2 minutes (было 5 — ускорено для более быстрой реакции)
    scheduler.add_job(
        pipeline.run_breaking, "interval", minutes=2,
        args=[bot, admin_id], id="breaking"
    )

    # Hourly digest — every hour at :01
    scheduler.add_job(
        pipeline.run_hourly, "cron", minute=1,
        args=[bot, admin_id], id="hourly"
    )

    # Morning review — 08:00 MSK
    scheduler.add_job(
        pipeline.run_morning, "cron", hour=8, minute=0,
        args=[bot, admin_id], id="morning"
    )

    # Evening review — 21:00 MSK
    scheduler.add_job(
        pipeline.run_evening, "cron", hour=21, minute=0,
        args=[bot, admin_id], id="evening"
    )

    # Weekly recap — Sunday at 20:00 MSK
    scheduler.add_job(
        pipeline.run_weekly, "cron", day_of_week="sun", hour=20, minute=0,
        args=[bot, admin_id], id="weekly"
    )

    # Monthly recap — last day of month at 21:30 MSK
    scheduler.add_job(
        pipeline.run_monthly, "cron", day="last", hour=21, minute=30,
        args=[bot, admin_id], id="monthly"
    )

    # Exchange openings
    scheduler.add_job(
        pipeline.run_exchange_open, "cron", hour=3, minute=0,
        args=[bot, "Tokyo", "Nikkei 225"], id="tokyo"
    )
    scheduler.add_job(
        pipeline.run_exchange_open, "cron", hour=11, minute=0,
        args=[bot, "London", "FTSE 100"], id="london"
    )
    scheduler.add_job(
        pipeline.run_exchange_open, "cron", hour=17, minute=30,
        args=[bot, "New York", "S&P 500"], id="newyork"
    )

    # Track record — раз в час сверяем рекомендации старше 24ч с реальным
    # движением цены (yfinance), копим % попаданий
    scheduler.add_job(
        pipeline.check_recommendations, "interval", hours=1,
        args=[bot, admin_id], id="track_record"
    )

    # Лидеры роста/падения MOEX — раз в день, 19:00 МСК (после закрытия
    # основной сессии Мосбиржи, ~18:50 МСК)
    scheduler.add_job(
        pipeline.run_leaders, "cron", hour=19, minute=0,
        args=[bot, admin_id], id="moex_leaders"
    )

    return scheduler

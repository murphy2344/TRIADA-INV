import logging
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from modules import pipeline

logger = logging.getLogger(__name__)
MSK = pytz.timezone("Europe/Moscow")


def build_scheduler(bot, admin_id: str) -> AsyncIOScheduler:
    # misfire_grace_time=600 — если event loop был заблокирован (синхронные
    # сетевые вызовы) и задача не запустилась вовремя, она всё равно запустится
    # если опоздание < 10 минут. Раньше стояло 1 сек — и задачи массово пропускались.
    # coalesce=True — если пропущено несколько запусков подряд, запускает только один.
    # max_instances=1 — не запускает вторую копию задачи, пока первая ещё работает.
    scheduler = AsyncIOScheduler(
        timezone=MSK,
        job_defaults={
            "misfire_grace_time": 600,
            "coalesce": True,
            "max_instances": 1,
        },
    )

    # Breaking news — каждые 2 минуты
    scheduler.add_job(
        pipeline.run_breaking, "interval", minutes=2,
        args=[bot, admin_id], id="breaking"
    )

    # Hourly digest — каждый час в :01
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
    # движением цены и ПУБЛИКУЕМ результат в канал
    scheduler.add_job(
        pipeline.check_recommendations, "interval", hours=1,
        args=[bot, admin_id], id="track_record"
    )

    # Лидеры роста/падения MOEX — раз в день, 19:00 МСК
    scheduler.add_job(
        pipeline.run_leaders, "cron", hour=19, minute=0,
        args=[bot, admin_id], id="moex_leaders"
    )

    # Пульс рынка (USD/RUB, IMOEX) — каждые 15 минут
    scheduler.add_job(
        pipeline.update_market_pulse, "interval", minutes=15,
        args=[bot, admin_id], id="market_pulse"
    )

    # Экономический календарь — недельный дайджест по понедельникам 09:00 МСК
    scheduler.add_job(
        pipeline.run_econ_calendar_weekly, "cron", day_of_week="mon", hour=9, minute=0,
        args=[bot, admin_id], id="econ_calendar_weekly"
    )
    # Экономический календарь — проверка "сегодня" каждое утро 08:30 МСК
    scheduler.add_job(
        pipeline.run_econ_calendar_today, "cron", hour=8, minute=30,
        args=[bot, admin_id], id="econ_calendar_today"
    )

    # Технические алерты (RSI/SMA) — раз в час
    scheduler.add_job(
        pipeline.run_technical_alerts, "interval", hours=1,
        args=[bot, admin_id], id="technical_alerts"
    )

    # Мониторинг выбранных Telegram-каналов — не чаще раза в 5 минут
    scheduler.add_job(
        pipeline.run_telegram_monitor, "interval", minutes=5,
        args=[bot, admin_id], id="telegram_monitor"
    )

    # Дайджест отчётностей компаний — раз в день, 09:30 МСК
    scheduler.add_job(
        pipeline.run_earnings_digest, "cron", hour=9, minute=30,
        args=[bot, admin_id], id="earnings_digest"
    )

    # Тепловая карта секторов — раз в день, 23:30 МСК
    scheduler.add_job(
        pipeline.run_sector_heatmap, "cron", hour=23, minute=30,
        args=[bot, admin_id], id="sector_heatmap"
    )

    # COT (Commitments of Traders) — по пятницам в 23:00 МСК
    # CFTC публикует отчёт по пятницам в 15:30 EST = ~22:30 МСК, ставим 23:00 с запасом
    scheduler.add_job(
        pipeline.run_cot_report, "cron", day_of_week="fri", hour=23, minute=0,
        args=[bot, admin_id], id="cot_report"
    )

    # 13F Filings — квартальные отчёты крупных фондов, раз в неделю пн 10:00 МСК
    # Данные меняются раз в квартал, чаще проверять бессмысленно
    scheduler.add_job(
        pipeline.run_13f_digest, "cron", day_of_week="mon", hour=10, minute=0,
        args=[bot, admin_id], id="filings_13f"
    )

    return scheduler

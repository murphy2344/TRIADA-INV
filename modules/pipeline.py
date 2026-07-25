import asyncio
import logging
from datetime import datetime
import pytz

from modules import news_sources, ai_analyzer, charting, media, formatter
from modules import dedup, storage, telegram_sender, critic, moex_leaders, market_pulse, econ_calendar, earnings, sector_heatmap
from config.config import ADMIN_ID

logger = logging.getLogger(__name__)
MSK = pytz.timezone("Europe/Moscow")


def _is_relevant(analysis: dict) -> bool:
    if analysis is None:
        return False
    if analysis.get("relevant") is False:
        return False
    if analysis.get("post_type") == "skip":
        return False
    return True


async def _get_media(
    analysis: dict,
    rss_image: str | None = None,
    post_category: str = "market",
) -> bytes | str | None:
    needs_chart = analysis.get("needs_chart", False)
    ticker = analysis.get("ticker")

    if needs_chart and ticker:
        chart = charting.build_chart(ticker)
        if chart:
            logger.info(f"Media: chart for {ticker}")
            return chart
        logger.warning(f"Chart failed for {ticker}, falling back to photo")

    subject    = analysis.get("subject", "financial markets")
    subject_en = analysis.get("subject_en", "")
    photo = await media.get_photo(
        subject=subject,
        subject_en=subject_en,
        rss_image=rss_image,
        post_category=post_category,
        ticker=ticker,
    )
    return photo


async def _track_recommendation(analysis: dict):
    """Сохраняет рекомендацию с текущей ценой для трек-рекорда — только
    если есть тикер и рекомендация не 'neutral' (нейтральную нельзя
    проверить на попадание — нет чёткого направления)."""
    ticker = analysis.get("ticker")
    recommendation = analysis.get("recommendation", "neutral")
    if not ticker or recommendation == "neutral":
        return
    price = charting.get_current_price(ticker)
    if price is None:
        return
    await storage.save_recommendation(
        ticker, analysis.get("subject", ""), recommendation, price
    )


async def run_breaking(bot, admin_id: str = None):
    news_list = news_sources.fetch_breaking_news(limit_per_feed=2)
    posted = 0
    for item in news_list:
        if await dedup.is_duplicate(item["id"], item["title"]):
            continue

        text = f"{item['title']}. {item.get('summary', '')}"
        analysis = ai_analyzer.analyze(text, "BREAKING")

        if not _is_relevant(analysis):
            logger.info(f"Skipped (not relevant): {item['title'][:60]}")
            continue

        # Вторая проверка на дубль — по теме+категории, независимо от
        # текста/языка заголовка (ловит одно и то же событие с разных
        # источников, даже если заголовки сильно отличаются)
        subject_en = analysis.get("subject_en", "")
        category = analysis.get("category", "market_move")
        if await dedup.is_duplicate_event(subject_en, category):
            logger.info(f"Skipped (duplicate event): {subject_en} / {category}")
            continue

        # AI-критик: второе мнение через ДРУГУЮ модель (Gemini), только для
        # высокого влияния — не тратим ограниченный бесплатный лимит Gemini
        # на каждую новость. Если критик не согласен — показываем оба взгляда
        # прозрачно вместо одного самоуверенного вывода (см. Pantheon).
        if analysis.get("impact_level") == "high":
            critic_result = critic.review(
                analysis.get("summary", ""),
                analysis.get("recommendation", "neutral"),
                analysis.get("recommendation_text", ""),
            )
            if critic_result:
                analysis["_critic"] = critic_result

        media_obj = await _get_media(analysis, rss_image=item.get("rss_image"), post_category="urgent")
        # Если ни RSS-фото, ни Wikimedia/CSE/Pexels не нашли ничего — используем стаб
        if media_obj is None:
            media_obj = "assets/stubs/hourly.jpg"

        chip_data = None
        ticker = analysis.get("ticker")
        if ticker:
            try:
                chip_data = await asyncio.to_thread(charting.get_sparkline_data, ticker, "1d")
            except Exception as e:
                logger.warning(f"Chip data fetch failed for {ticker}: {e}")

        caption = formatter.fmt_breaking(analysis, item["source"], item["url"], chip_data)

        ok = await telegram_sender.send_photo_text(bot, media_obj, caption)
        if ok:
            await storage.mark_published(item["id"], item["title"], item["source"], item["url"], "BREAKING")
            await dedup.mark_as_published(item["id"], item["title"])
            await dedup.mark_event_published(subject_en, category)
            await storage.increment_stats()
            await _track_recommendation(analysis)
            posted += 1
        else:
            if admin_id:
                await telegram_sender.notify_admin(
                    bot, admin_id,
                    f"❌ Пост не вышел (BREAKING):\n<b>{item['title'][:100]}</b>\nОшибка отправки."
                )
    return posted


async def run_hourly(bot, admin_id: str = None):
    news_list = news_sources.fetch_news(limit_per_feed=3)
    fresh = []
    for item in news_list:
        if not await dedup.is_duplicate(item["id"], item["title"]):
            fresh.append(item)
        if len(fresh) >= 4:
            break

    if not fresh:
        return 0

    analyses = ai_analyzer.analyze_batch(fresh, "HOURLY")
    if not analyses:
        if admin_id:
            await telegram_sender.notify_admin(bot, admin_id, "❌ Часовой обзор: нет релевантных новостей.")
        return 0

    # Отфильтровываем повторы событий (по теме+категории), даже если
    # заголовки с разных источников отличаются текстуально
    filtered_analyses = []
    for a in analyses:
        subject_en = a.get("subject_en", "")
        category = a.get("category", "market_move")
        if await dedup.is_duplicate_event(subject_en, category):
            logger.info(f"Hourly: skip duplicate event {subject_en}/{category}")
            continue
        filtered_analyses.append(a)
    analyses = filtered_analyses

    if not analyses:
        return 0

    now    = datetime.now(MSK)
    header = formatter.fmt_hourly_header(now)
    body   = formatter.fmt_hourly_body(analyses)
    photo  = "assets/stubs/hourly.jpg"
    ok     = await telegram_sender.send_two_messages(bot, photo, header, body)

    if ok:
        for item in fresh:
            await storage.mark_published(item["id"], item["title"], item["source"], item["url"], "HOURLY")
            await dedup.mark_as_published(item["id"], item["title"])
        for a in analyses:
            await dedup.mark_event_published(a.get("subject_en", ""), a.get("category", "market_move"))
        await storage.increment_stats()
        return 1
    else:
        if admin_id:
            await telegram_sender.notify_admin(bot, admin_id, "❌ Часовой обзор не вышел. Ошибка отправки.")
        return 0


async def run_morning(bot, admin_id: str = None):
    news_list = news_sources.fetch_news(limit_per_feed=4)
    fresh = [i for i in news_list if not await dedup.is_duplicate(i["id"], i["title"])][:4]

    fng      = await _get_fear_greed()
    now      = datetime.now(MSK)
    date_str = now.strftime("%d %B %Y")

    analyses       = ai_analyzer.analyze_batch(fresh, "MORNING") if fresh else []
    header, body   = formatter.fmt_morning(analyses, date_str, fng)
    photo          = "assets/stubs/morning.jpg"
    ok             = await telegram_sender.send_two_messages(bot, photo, header, body)

    if ok:
        for item in fresh:
            await storage.mark_published(item["id"], item["title"], item["source"], item["url"], "MORNING")
            await dedup.mark_as_published(item["id"], item["title"])
        await storage.increment_stats()
        return 1
    else:
        if admin_id:
            await telegram_sender.notify_admin(bot, admin_id, "❌ Утренний обзор не вышел.")
        return 0


async def run_evening(bot, admin_id: str = None):
    news_list = news_sources.fetch_news(limit_per_feed=4)
    fresh = [i for i in news_list if not await dedup.is_duplicate(i["id"], i["title"])][:4]

    fng      = await _get_fear_greed()
    now      = datetime.now(MSK)
    date_str = now.strftime("%d %B %Y")

    analyses     = ai_analyzer.analyze_batch(fresh, "EVENING") if fresh else []
    header, body = formatter.fmt_evening(analyses, date_str, fng)
    photo        = "assets/stubs/evening.jpg"
    ok           = await telegram_sender.send_two_messages(bot, photo, header, body)

    if ok:
        for item in fresh:
            await storage.mark_published(item["id"], item["title"], item["source"], item["url"], "EVENING")
            await dedup.mark_as_published(item["id"], item["title"])
        await storage.increment_stats()
        return 1
    else:
        if admin_id:
            await telegram_sender.notify_admin(bot, admin_id, "❌ Вечерний обзор не вышел.")
        return 0


async def run_weekly(bot, admin_id: str = None):
    news_list = news_sources.fetch_news(limit_per_feed=5)
    analyses  = ai_analyzer.analyze_batch(news_list[:5], "WEEKLY") if news_list else []
    fng       = await _get_fear_greed()
    accuracy  = await storage.get_accuracy_stats(days=7)
    header, body = formatter.fmt_weekly(analyses, fng, accuracy)
    photo     = "assets/stubs/weekly.jpg"
    ok        = await telegram_sender.send_two_messages(bot, photo, header, body)
    if ok:
        await storage.increment_stats()
        return 1
    return 0


async def run_monthly(bot, admin_id: str = None):
    news_list = news_sources.fetch_news(limit_per_feed=6)
    analyses  = ai_analyzer.analyze_batch(news_list[:6], "MONTHLY") if news_list else []
    header, body = formatter.fmt_monthly(analyses)
    photo     = "assets/stubs/monthly.jpg"
    ok        = await telegram_sender.send_two_messages(bot, photo, header, body)
    if ok:
        await storage.increment_stats()
        return 1
    return 0


async def run_exchange_open(bot, exchange: str, index: str):
    now  = datetime.now(MSK)
    text = formatter.fmt_exchange_open(exchange, index, now)
    photo = "assets/stubs/exchange.jpg"
    await telegram_sender.send_photo_text(bot, photo, text)


async def run_leaders(bot, admin_id: str = None) -> int:
    """Лидеры роста/падения MOEX по всем 4 периодам. Синхронный сетевой код
    (requests) выполняется в отдельном потоке, чтобы не блокировать event loop."""
    try:
        all_periods = await asyncio.to_thread(moex_leaders.get_all_periods_leaders, 5)
    except Exception as e:
        logger.error(f"MOEX leaders error: {e}")
        if admin_id:
            await telegram_sender.notify_admin(
                bot, admin_id, f"❌ Не удалось получить данные MOEX: {e}"
            )
        return 0

    header, body = formatter.fmt_leaders(all_periods)
    photo = "assets/stubs/moex.jpg"
    ok = await telegram_sender.send_photo_text(bot, photo, f"{header}\n\n{body}")
    if ok:
        await storage.increment_stats()
        return 1
    return 0


async def update_market_pulse(bot, admin_id: str = None):
    """Обновляет закреплённое сообщение с курсом USD/RUB и IMOEX. Вызывается
    по расписанию (см. scheduler.py) — редактирует существующее сообщение
    вместо создания нового поста при каждом обновлении."""
    try:
        text = await asyncio.to_thread(market_pulse.build_pulse_text)
        current_id = await storage.get_meta("pulse_message_id")
        new_id = await telegram_sender.update_pinned_message(bot, text, current_id)
        if new_id and new_id != current_id:
            await storage.set_meta("pulse_message_id", new_id)
        return bool(new_id)
    except Exception as e:
        logger.error(f"update_market_pulse error: {e}")
        if admin_id:
            await telegram_sender.notify_admin(bot, admin_id, f"❌ Не удалось обновить пульс рынка: {e}")
        return False


async def run_sector_heatmap(bot, admin_id: str = None) -> int:
    try:
        changes = await asyncio.to_thread(sector_heatmap.fetch_sector_changes)
        if not changes:
            return 0
        text = formatter.fmt_sector_heatmap(changes, sector_heatmap.SECTORS)
        image = await asyncio.to_thread(sector_heatmap.generate_heatmap_image, changes)
        ok = await telegram_sender.send_photo_text(bot, image, text)
        if ok:
            await storage.increment_stats()
            return 1
        return 0
    except Exception as e:
        logger.error(f"run_sector_heatmap error: {e}")
        if admin_id:
            await telegram_sender.notify_admin(bot, admin_id, f"❌ Тепловая карта секторов: {e}")
        return 0


async def run_earnings_digest(bot, admin_id: str = None) -> int:
    posted = 0
    try:
        upcoming = await asyncio.to_thread(earnings.check_upcoming, 3)
        text_upcoming = formatter.fmt_earnings_upcoming(upcoming)
        if text_upcoming:
            if await telegram_sender.send_text(bot, text_upcoming):
                await storage.increment_stats()
                posted += 1

        recent = await asyncio.to_thread(earnings.check_recent_results, 2)
        # антидубль: не публиковать повторно тот же отчёт компании
        new_recent = []
        for r in recent:
            key = f"earnings:{r['ticker']}:{r['date'].date().isoformat()}"
            if not await storage.get_meta(key):
                new_recent.append(r)
                await storage.set_meta(key, "posted")
        text_recent = formatter.fmt_earnings_recent(new_recent)
        if text_recent:
            if await telegram_sender.send_text(bot, text_recent):
                await storage.increment_stats()
                posted += 1

        return posted
    except Exception as e:
        logger.error(f"run_earnings_digest error: {e}")
        if admin_id:
            await telegram_sender.notify_admin(bot, admin_id, f"❌ Дайджест отчётностей: {e}")
        return posted


async def run_technical_alerts(bot, admin_id: str = None) -> int:
    """Проверяет watchlist на технические сигналы (RSI, скользящие средние).
    Не спамит одним и тем же сигналом чаще раза в 24 часа на тикер+сигнал."""
    import modules.technical_alerts as technical_alerts

    posted = 0
    try:
        await storage.clear_stale_alerts(cooldown_hours=24)
    except Exception as e:
        logger.error(f"clear_stale_alerts error: {e}")

    for ticker in technical_alerts.WATCHLIST:
        try:
            info = await asyncio.to_thread(technical_alerts.analyze_ticker, ticker)
            signals = technical_alerts.detect_signals(info)
            new_signals = []
            for s in signals:
                if not await storage.was_alerted_recently(ticker, s["type"]):
                    new_signals.append(s)
                    await storage.mark_alerted(ticker, s["type"])
            if not new_signals:
                continue

            text = formatter.fmt_technical_alert(ticker, new_signals)
            ok = await telegram_sender.send_text(bot, text)
            if ok:
                await storage.increment_stats()
                posted += 1
        except Exception as e:
            logger.error(f"run_technical_alerts error ({ticker}): {e}")
            continue

    return posted


async def run_econ_calendar_weekly(bot, admin_id: str = None) -> int:
    try:
        releases = await asyncio.to_thread(econ_calendar.fetch_upcoming, 7)
        text = formatter.fmt_econ_calendar_weekly(releases)
        if not text:
            return 0
        ok = await telegram_sender.send_text(bot, text)
        if ok:
            await storage.increment_stats()
            return 1
        return 0
    except Exception as e:
        logger.error(f"run_econ_calendar_weekly error: {e}")
        if admin_id:
            await telegram_sender.notify_admin(bot, admin_id, f"❌ Экономкалендарь (неделя): {e}")
        return 0


async def run_econ_calendar_today(bot, admin_id: str = None) -> int:
    try:
        releases = await asyncio.to_thread(econ_calendar.get_today_releases)
        text = formatter.fmt_econ_calendar_today(releases)
        if not text:
            return 0
        ok = await telegram_sender.send_text(bot, text)
        if ok:
            await storage.increment_stats()
            return 1
        return 0
    except Exception as e:
        logger.error(f"run_econ_calendar_today error: {e}")
        if admin_id:
            await telegram_sender.notify_admin(bot, admin_id, f"❌ Экономкалендарь (сегодня): {e}")
        return 0


async def check_recommendations(bot=None, admin_id: str = None):
    """Сверяет рекомендации старше 24 часов с реальным движением цены.
    Long считается верным, если цена выросла; Short — если упала."""
    pending = await storage.get_unchecked_recommendations(older_than_hours=24)
    for rec in pending:
        price_after = charting.get_current_price(rec["ticker"])
        if price_after is None:
            continue
        went_up = price_after > rec["price_at_post"]
        correct = went_up if rec["recommendation"] == "long" else not went_up
        await storage.update_recommendation_result(rec["id"], price_after, correct)
    return len(pending)


async def _get_fear_greed() -> str:
    import aiohttp
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.alternative.me/fng/",
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                data = await r.json()
                val = data["data"][0]["value"]
                cls = data["data"][0]["value_classification"]
                return f"📊 Индекс страха и жадности: <b>{val} ({cls})</b>"
    except Exception:
        return ""

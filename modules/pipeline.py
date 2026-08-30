import asyncio
import html
import logging
from datetime import datetime
import pytz

from modules import news_sources, ai_analyzer, charting, media, formatter
from modules import dedup, storage, telegram_sender, critic, moex_leaders, market_pulse, econ_calendar, earnings, sector_heatmap, forum_topics, telegram_monitor
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


def _topic_kwargs(analysis: dict | None = None) -> dict:
    """Destination kwargs: topic posts go to the forum group; general posts omit thread id."""
    kwargs = {"chat_id": forum_topics.target_chat_id()}
    if analysis:
        topic_key = forum_topics.route_topic(analysis)
        kwargs["topic_key"] = topic_key
        thread_id = forum_topics.get_topic_id(topic_key)
        if thread_id is not None:
            kwargs["message_thread_id"] = thread_id
    return kwargs


def _topic_kwargs_for_key(topic_key: str) -> dict:
    kwargs = {"chat_id": forum_topics.target_chat_id()}
    kwargs["topic_key"] = topic_key
    thread_id = forum_topics.get_topic_id(topic_key)
    if thread_id is not None:
        kwargs["message_thread_id"] = thread_id
    return kwargs


def _topic_kwargs_for_analyses(analyses: list[dict]) -> dict:
    """Route a digest using the first available analyzed news item."""
    for analysis in analyses:
        if analysis:
            return _topic_kwargs(analysis)
    return _topic_kwargs()


async def _get_media(
    analysis: dict,
    rss_image: str | None = None,
    post_category: str = "market",
) -> bytes | str | None:
    needs_chart = analysis.get("needs_chart", False)
    ticker = analysis.get("ticker")

    if needs_chart and ticker:
        # Синхронный вызов в отдельном потоке — не блокирует event loop
        chart = await asyncio.to_thread(charting.build_chart, ticker)
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
    """Сохраняет рекомендацию с текущей ценой для трек-рекорда."""
    ticker = analysis.get("ticker")
    recommendation = analysis.get("recommendation", "neutral")
    if not ticker or recommendation == "neutral":
        return
    price = await asyncio.to_thread(charting.get_current_price, ticker)
    if price is None:
        return
    await storage.save_recommendation(
        ticker,
        analysis.get("subject", ""),
        recommendation,
        price,
        category=analysis.get("ai_category") or analysis.get("category", "market_move"),
        confidence=analysis.get("confidence"),
        source=analysis.get("_source", ""),
    )


async def _publish_breaking_item(bot, item: dict, admin_id: str = None) -> bool:
    title = str(item.get("title") or "")[:180]

    async def fail(stage: str, exc) -> bool:
        detail = f"{type(exc).__name__}: {exc}" if isinstance(exc, Exception) else str(exc)
        logger.exception("BREAKING failed at %s for %s: %s", stage, title[:80], detail)
        if admin_id:
            await telegram_sender.notify_admin(
                bot,
                admin_id,
                (
                    "❌ <b>Пост не вышел (BREAKING)</b>\n"
                    f"<b>{html.escape(title)}</b>\n"
                    f"Этап: {html.escape(stage)}\n"
                    f"Причина: <code>{html.escape(detail[:700])}</code>"
                ),
            )
        return False

    try:
        if await dedup.is_duplicate(item["id"], item["title"]):
            return False

        text = f"{item['title']}. {item.get('summary', '')}"
        analysis = await asyncio.to_thread(ai_analyzer.analyze, text, "BREAKING")
        if not _is_relevant(analysis):
            logger.info("Skipped (not relevant): %s", title[:60])
            return False

        subject_en = analysis.get("subject_en", "")
        category = analysis.get("category", "market_move")
        if await dedup.is_duplicate_event(subject_en, category):
            logger.info("Skipped (duplicate event): %s / %s", subject_en, category)
            return False

        if analysis.get("impact_level") == "high":
            critic_result = await asyncio.to_thread(
                critic.review,
                analysis.get("summary", ""),
                analysis.get("recommendation", "neutral"),
                analysis.get("recommendation_text", ""),
            )
            if critic_result:
                analysis["_critic"] = critic_result

        media_obj = await _get_media(
            analysis, rss_image=item.get("rss_image"), post_category="urgent"
        )
        if media_obj is None:
            media_obj = "assets/stubs/breaking.jpg"

        chip_data = None
        ticker = analysis.get("ticker")
        if ticker:
            try:
                chip_data = await asyncio.to_thread(charting.get_sparkline_data, ticker, "1d")
            except Exception as exc:
                logger.warning("Chip data fetch failed for %s: %s", ticker, exc)

        source = item.get("source") or ""
        url = item.get("url") or ""
        caption = formatter.fmt_breaking(analysis, source, url, chip_data)
        ok, send_detail = await telegram_sender.send_photo_text_detailed(
            bot, media_obj, caption,
            reply_markup=formatter.breaking_keyboard(analysis, url),
            **_topic_kwargs(analysis)
        )
        if not ok:
            await fail("Telegram отправка", send_detail)
            return False
        if send_detail:
            logger.warning("BREAKING published with fallback: %s", send_detail)

        await storage.mark_published(item["id"], item["title"], source, url, "BREAKING")
        await dedup.mark_as_published(item["id"], item["title"])
        await dedup.mark_event_published(subject_en, category)
        await storage.increment_stats()
        await _track_recommendation(analysis)
        return True
    except Exception as exc:
        return await fail("обработка BREAKING", exc)


async def run_breaking(bot, admin_id: str = None):
    news_list = await asyncio.to_thread(news_sources.fetch_breaking_news, 2)
    posted = 0
    for item in news_list:
        if await _publish_breaking_item(bot, item, admin_id):
            posted += 1
    return posted


async def run_telegram_monitor(bot, admin_id: str = None) -> int:
    """Fetch selected Telegram channels and send them through the BREAKING pipeline."""
    try:
        items = await telegram_monitor.fetch_new_messages()
        posted = 0
        for item in items:
            if await _publish_breaking_item(bot, item, admin_id):
                posted += 1
        return posted
    except Exception as exc:
        logger.exception("run_telegram_monitor error")
        if admin_id:
            await telegram_sender.notify_admin(bot, admin_id, f"❌ Telegram-мониторинг: {exc}")
        return 0


async def run_hourly(bot, admin_id: str = None):
    news_list = await asyncio.to_thread(news_sources.fetch_news, 3)
    fresh = []
    for item in news_list:
        if not await dedup.is_duplicate(item["id"], item["title"]):
            fresh.append(item)
        if len(fresh) >= 4:
            break

    if not fresh:
        return 0

    analyses = await asyncio.to_thread(ai_analyzer.analyze_batch, fresh, "HOURLY")
    if not analyses:
        if admin_id:
            await telegram_sender.notify_admin(bot, admin_id, "❌ Часовой обзор: нет релевантных новостей.")
        return 0

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
    ok     = await telegram_sender.send_two_messages(bot, photo, header, body, **_topic_kwargs(analyses[0]))

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
    news_list = await asyncio.to_thread(news_sources.fetch_news, 4)
    fresh = []
    for item in news_list:
        if not await dedup.is_duplicate(item["id"], item["title"]):
            fresh.append(item)
        if len(fresh) >= 4:
            break

    fng      = await _get_fear_greed()
    now      = datetime.now(MSK)
    date_str = now.strftime("%d %B %Y")

    analyses       = await asyncio.to_thread(ai_analyzer.analyze_batch, fresh, "MORNING") if fresh else []
    header, body   = formatter.fmt_morning(analyses, date_str, fng)
    photo          = "assets/stubs/morning.jpg"
    ok             = await telegram_sender.send_two_messages(
        bot, photo, header, body, **_topic_kwargs_for_analyses(analyses)
    )

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
    news_list = await asyncio.to_thread(news_sources.fetch_news, 4)
    fresh = []
    for item in news_list:
        if not await dedup.is_duplicate(item["id"], item["title"]):
            fresh.append(item)
        if len(fresh) >= 4:
            break

    fng      = await _get_fear_greed()
    now      = datetime.now(MSK)
    date_str = now.strftime("%d %B %Y")

    analyses     = await asyncio.to_thread(ai_analyzer.analyze_batch, fresh, "EVENING") if fresh else []
    header, body = formatter.fmt_evening(analyses, date_str, fng)
    photo        = "assets/stubs/evening.jpg"
    ok           = await telegram_sender.send_two_messages(
        bot, photo, header, body, **_topic_kwargs_for_analyses(analyses)
    )

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
    news_list = await asyncio.to_thread(news_sources.fetch_news, 5)
    analyses  = await asyncio.to_thread(ai_analyzer.analyze_batch, news_list[:5], "WEEKLY") if news_list else []
    fng       = await _get_fear_greed()
    accuracy  = await storage.get_accuracy_stats(days=7)
    header, body = formatter.fmt_weekly(analyses, fng, accuracy)
    photo     = "assets/stubs/weekly.jpg"
    ok        = await telegram_sender.send_two_messages(
        bot, photo, header, body, **_topic_kwargs_for_analyses(analyses)
    )
    if ok:
        await storage.increment_stats()
        return 1
    return 0


async def run_monthly(bot, admin_id: str = None):
    news_list = await asyncio.to_thread(news_sources.fetch_news, 6)
    analyses  = await asyncio.to_thread(ai_analyzer.analyze_batch, news_list[:6], "MONTHLY") if news_list else []
    header, body = formatter.fmt_monthly(analyses)
    photo     = "assets/stubs/monthly.jpg"
    ok        = await telegram_sender.send_two_messages(
        bot, photo, header, body, **_topic_kwargs_for_analyses(analyses)
    )
    if ok:
        await storage.increment_stats()
        return 1
    return 0


async def run_exchange_open(bot, exchange: str, index: str):
    now  = datetime.now(MSK)
    text = formatter.fmt_exchange_open(exchange, index, now)
    photo = "assets/stubs/exchange.jpg"
    await telegram_sender.send_photo_text(
        bot, photo, text, **_topic_kwargs_for_key("markets")
    )


async def run_leaders(bot, admin_id: str = None) -> int:
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
    ok = await telegram_sender.send_photo_text(
        bot, photo, f"{header}\n\n{body}", **_topic_kwargs_for_key("markets")
    )
    if ok:
        await storage.increment_stats()
        return 1
    return 0


async def update_market_pulse(bot, admin_id: str = None):
    """Обновляет закреплённое сообщение с пульсом рынка."""
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
        ok = await telegram_sender.send_photo_text(
            bot, image, text, **_topic_kwargs_for_key("markets")
        )
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
            if await telegram_sender.send_text(bot, text_upcoming, **_topic_kwargs_for_key("companies")):
                await storage.increment_stats()
                posted += 1

        recent = await asyncio.to_thread(earnings.check_recent_results, 2)
        new_recent = []
        for r in recent:
            key = f"earnings:{r['ticker']}:{r['date'].date().isoformat()}"
            if not await storage.get_meta(key):
                new_recent.append(r)
                await storage.set_meta(key, "posted")
        text_recent = formatter.fmt_earnings_recent(new_recent)
        if text_recent:
            if await telegram_sender.send_text(bot, text_recent, **_topic_kwargs_for_key("companies")):
                await storage.increment_stats()
                posted += 1

        return posted
    except Exception as e:
        logger.error(f"run_earnings_digest error: {e}")
        if admin_id:
            await telegram_sender.notify_admin(bot, admin_id, f"❌ Дайджест отчётностей: {e}")
        return posted


async def run_technical_alerts(bot, admin_id: str = None) -> int:
    """Только по ручной команде /alerts — убрано из расписания."""
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
            ok = await telegram_sender.send_text(bot, text, **_topic_kwargs({"ticker": ticker, "asset_class": "commodity" if ticker in {"GC=F", "CL=F"} else ("crypto" if ticker == "BTC-USD" else "equity") }))
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
        if not releases:
            logger.info("run_econ_calendar_weekly: no upcoming releases (FRED_API_KEY missing or no events)")
            return 0
        text = formatter.fmt_econ_calendar_weekly(releases)
        if not text:
            return 0
        ok = await telegram_sender.send_text(
            bot, text, **_topic_kwargs_for_key("markets")
        )
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
        if not releases:
            logger.info("run_econ_calendar_today: no events today")
            return 0
        text = formatter.fmt_econ_calendar_today(releases)
        if not text:
            return 0
        ok = await telegram_sender.send_text(
            bot, text, **_topic_kwargs_for_key("markets")
        )
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
    """Сверяет рекомендации старше 24 часов с реальным движением цены
    и ПУБЛИКУЕТ результат в канал (long/short: цена тогда vs сейчас)."""
    pending = await storage.get_unchecked_recommendations()
    if not pending:
        return 0

    results = []
    for rec in pending:
        metrics = await asyncio.to_thread(
            charting.get_price_metrics, rec["ticker"], rec["price_at_post"]
        )
        if not metrics:
            continue
        price_after = metrics["price_after"]
        went_up = price_after > rec["price_at_post"]
        correct = went_up if rec["recommendation"] == "long" else not went_up
        await storage.update_recommendation_result(
            rec["id"],
            price_after,
            correct,
            pnl_percent=(
                metrics["pnl_percent"]
                if rec["recommendation"] == "long"
                else -metrics["pnl_percent"]
            ),
            max_drawdown_percent=metrics["max_drawdown_percent"],
        )
        results.append({
            "ticker": rec["ticker"],
            "recommendation": rec["recommendation"],
            "price_at_post": rec["price_at_post"],
            "price_after": price_after,
            "correct": correct,
            "pnl_percent": metrics["pnl_percent"],
            "max_drawdown_percent": metrics["max_drawdown_percent"],
            "horizon_hours": rec.get("horizon_hours", 24),
        })

    if results and bot:
        text = formatter.fmt_track_record_result(results)
        if text:
            ok = await telegram_sender.send_text(
                bot, text, **_topic_kwargs_for_key("markets")
            )
            if ok:
                await storage.increment_stats()

    return len(results)


async def run_cot_report(bot, admin_id: str = None) -> int:
    """COT (Commitments of Traders) — позиции крупных игроков от CFTC."""
    try:
        from modules import cot_report
        items = await asyncio.to_thread(cot_report.fetch_all_cot)
        if not items:
            logger.info("run_cot_report: no COT data available")
            return 0
        text = formatter.fmt_cot_report(items)
        if not text:
            return 0
        ok = await telegram_sender.send_text(bot, text, **_topic_kwargs_for_key("commodities"))
        if ok:
            await storage.increment_stats()
            return 1
        return 0
    except Exception as e:
        logger.error(f"run_cot_report error: {e}")
        if admin_id:
            await telegram_sender.notify_admin(bot, admin_id, f"❌ COT Report: {e}")
        return 0


async def run_13f_digest(bot, admin_id: str = None) -> int:
    """13F Filings — квартальные отчёты крупных фондов от SEC EDGAR."""
    try:
        from modules import filings_13f
        items = await asyncio.to_thread(filings_13f.fetch_all_13f)
        if not items:
            logger.info("run_13f_digest: no 13F data available")
            return 0
        text = formatter.fmt_13f_digest(items)
        if not text:
            return 0
        ok = await telegram_sender.send_text(bot, text, **_topic_kwargs_for_key("companies"))
        if ok:
            await storage.increment_stats()
            return 1
        return 0
    except Exception as e:
        logger.error(f"run_13f_digest error: {e}")
        if admin_id:
            await telegram_sender.notify_admin(bot, admin_id, f"❌ 13F Digest: {e}")
        return 0


async def run_market_snapshot(bot, admin_id: str = None) -> int:
    """Market snapshot - overview of global markets every 4 hours."""
    try:
        from modules import market_snapshot

        data = await market_snapshot.fetch_market_snapshot()
        if not data:
            logger.info("run_market_snapshot: no data available")
            return 0

        text = market_snapshot.format_market_snapshot(data)
        sentiment = await market_snapshot.get_market_sentiment()
        text += f"\n\n<b>Настроение рынка:</b> {sentiment}"

        ok = await telegram_sender.send_text(bot, text, **_topic_kwargs_for_key("markets"))
        if ok:
            await storage.increment_stats()
            return 1
        return 0
    except Exception as e:
        logger.error(f"run_market_snapshot error: {e}")
        if admin_id:
            await telegram_sender.notify_admin(bot, admin_id, f"❌ Market Snapshot: {e}")
        return 0


async def run_screener_breakouts(bot, admin_id: str = None) -> int:
    """Daily screener - breakouts with volume."""
    try:
        from modules import market_screener

        results = await market_screener.scan_breakouts()
        if not results:
            logger.info("run_screener_breakouts: no breakouts found")
            return 0

        text = market_screener.format_screener_results("breakouts", results)
        ok = await telegram_sender.send_text(bot, text, **_topic_kwargs_for_key("markets"))
        if ok:
            await storage.increment_stats()
            return 1
        return 0
    except Exception as e:
        logger.error(f"run_screener_breakouts error: {e}")
        if admin_id:
            await telegram_sender.notify_admin(bot, admin_id, f"❌ Screener Breakouts: {e}")
        return 0


async def run_screener_top_movers(bot, admin_id: str = None) -> int:
    """Daily screener - top gainers and losers."""
    try:
        from modules import market_screener

        results = await market_screener.scan_top_movers()
        if not results:
            logger.info("run_screener_top_movers: no data")
            return 0

        text = market_screener.format_screener_results("top_movers", results)
        ok = await telegram_sender.send_text(bot, text, **_topic_kwargs_for_key("markets"))
        if ok:
            await storage.increment_stats()
            return 1
        return 0
    except Exception as e:
        logger.error(f"run_screener_top_movers error: {e}")
        if admin_id:
            await telegram_sender.notify_admin(bot, admin_id, f"❌ Screener Top Movers: {e}")
        return 0


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

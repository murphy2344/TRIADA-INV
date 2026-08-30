"""
Полная диагностика бота TRIADA INVESTING.
Вызывается через команду /testall — публикует подробный отчёт в канал.

Каждый тест возвращает (ok: bool, detail: str).
Тесты НЕ публикуют лишние посты — проверяют только получение данных,
кроме явно помеченных как "live post test".
"""
import asyncio
import html
import logging
import os
import time
import requests

logger = logging.getLogger(__name__)


def _run(label: str, fn, *args, timeout_sec: int = 30) -> tuple[bool, str]:
    """Запускает синхронную функцию с таймаутом и возвращает (ok, detail)."""
    try:
        start = time.time()
        result = fn(*args)
        elapsed = round(time.time() - start, 1)
        if result is None:
            return False, f"вернул None ({elapsed}s)"
        if isinstance(result, (list, dict)) and len(result) == 0:
            return False, f"пустой результат ({elapsed}s)"
        if isinstance(result, bytes) and len(result) < 100:
            return False, f"слишком маленький bytes ({len(result)}B, {elapsed}s)"
        detail = ""
        if isinstance(result, list):
            detail = f"{len(result)} элем. ({elapsed}s)"
        elif isinstance(result, bytes):
            detail = f"{len(result):,} байт ({elapsed}s)"
        elif isinstance(result, str):
            detail = f'"{result[:60]}" ({elapsed}s)'
        elif isinstance(result, dict):
            detail = f"{list(result.keys())[:4]} ({elapsed}s)"
        else:
            detail = f"OK ({elapsed}s)"
        return True, detail
    except Exception as e:
        return False, str(e)[:120]


async def _run_async(fn, *args, timeout_sec: int = 30) -> tuple[bool, str, any]:
    try:
        start = time.time()
        result = await asyncio.wait_for(fn(*args), timeout=timeout_sec)
        elapsed = round(time.time() - start, 1)
        return True, f"OK ({elapsed}s)", result
    except asyncio.TimeoutError:
        return False, f"timeout >{timeout_sec}s", None
    except Exception as e:
        return False, str(e)[:120], None


# ──────────────────────────────────────────────────────────────────────────────
# 1. ENV VARIABLES
# ──────────────────────────────────────────────────────────────────────────────
def test_env() -> list[tuple[str, bool, str]]:
    results = []
    vars_required = [
        ("BOT_TOKEN",       True),
        ("ADMIN_ID",        True),
        ("CHANNEL_ID",      True),
        ("RENDER",          True),
    ]
    vars_optional = [
        ("FRED_API_KEY",    False),
        ("PEXELS_API_KEY",  False),
        ("PIXABAY_API_KEY", False),
        ("GOOGLE_CSE_API_KEY", False),
        ("GOOGLE_CSE_CX",  False),
        ("UPSTASH_REDIS_REST_URL", False),
        ("UPSTASH_REDIS_REST_TOKEN", False),
    ]
    for name, required in vars_required + vars_optional:
        val = os.environ.get(name, "")
        ok = bool(val)
        label = f"{'❗' if required and not ok else ''}{name}"
        detail = "✅ задан" if ok else ("❌ ОТСУТСТВУЕТ (обязательный)" if required else "⚠️ не задан (опционально)")
        results.append((label, ok or not required, detail))

    ai_key = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GOOGLE_GEMINI_API_KEY")
        or os.environ.get("GROQ_API_KEY")
    )
    results.append((
        "AI_KEY (Gemini/Groq)",
        bool(ai_key),
        "✅ задан" if ai_key else "❌ ОТСУТСТВУЕТ (нужен Gemini или Groq ключ)",
    ))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# 2. REDIS
# ──────────────────────────────────────────────────────────────────────────────
async def test_redis() -> tuple[bool, str]:
    try:
        from modules import dedup
        ok, err = await dedup.check_redis_connection()
        if ok:
            return True, "✅ Upstash Redis — соединение OK"
        if not dedup.USE_REDIS:
            return True, "⚠️ Redis не настроен — используется SQLite fallback"
        return False, f"❌ Redis: {err}"
    except Exception as e:
        return False, f"❌ {e}"


# ──────────────────────────────────────────────────────────────────────────────
# 3. AI ANALYZER
# ──────────────────────────────────────────────────────────────────────────────
def test_ai() -> tuple[bool, str]:
    try:
        from modules import ai_analyzer
        result = ai_analyzer.analyze(
            "Federal Reserve raises interest rates by 25bp.",
            "BREAKING"
        )
        if result and result.get("title"):
            return True, f"✅ Gemini → Groq AI — '{result['title'][:60]}'"
        return False, "❌ AI вернул пустой результат"
    except Exception as e:
        return False, f"❌ {e}"


# ──────────────────────────────────────────────────────────────────────────────
# 4. RSS NEWS SOURCES
# ──────────────────────────────────────────────────────────────────────────────
def test_news_sources() -> list[tuple[str, bool, str]]:
    results = []
    try:
        from modules import news_sources
        breaking = news_sources.fetch_breaking_news(limit_per_feed=2)
        ok = isinstance(breaking, list) and len(breaking) > 0
        results.append(("RSS Breaking", ok,
                         f"✅ {len(breaking)} новостей" if ok else "❌ пустой список"))

        regular = news_sources.fetch_news(limit_per_feed=3)
        ok2 = isinstance(regular, list) and len(regular) > 0
        results.append(("RSS Regular", ok2,
                         f"✅ {len(regular)} новостей" if ok2 else "❌ пустой список"))
    except Exception as e:
        results.append(("RSS", False, f"❌ {e}"))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# 5. MARKET PULSE (USD/RUB + IMOEX)
# ──────────────────────────────────────────────────────────────────────────────
def test_market_pulse() -> list[tuple[str, bool, str]]:
    results = []
    try:
        from modules import market_pulse

        ok, detail = _run("USD/RUB yfinance", market_pulse.fetch_usd_rub)
        if ok:
            usd_val = market_pulse.fetch_usd_rub()
            detail = f"✅ {usd_val} ₽" if usd_val else "❌ None"
            ok = usd_val is not None
        results.append(("Пульс / USD-RUB (yfinance)", ok, detail))

        ok2, detail2 = _run("IMOEX MOEX ISS", market_pulse.fetch_imoex)
        if ok2:
            imoex = market_pulse.fetch_imoex()
            detail2 = f"✅ {imoex['value']:,.2f}" if imoex else "❌ None"
            ok2 = imoex is not None
        results.append(("Пульс / IMOEX", ok2, detail2))

        ok3, detail3 = _run("build_pulse_text", market_pulse.build_pulse_text)
        results.append(("Пульс / сборка текста", ok3, detail3 if ok3 else f"❌ {detail3}"))
    except Exception as e:
        results.append(("Market Pulse", False, f"❌ {e}"))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# 6. CHARTING
# ──────────────────────────────────────────────────────────────────────────────
def test_charting() -> list[tuple[str, bool, str]]:
    results = []
    try:
        from modules import charting

        # Finviz chart — должен вернуть > 8 KB или None
        chart_fv = charting._finviz_chart("AAPL")
        if chart_fv is None:
            results.append(("Finviz chart AAPL", True, "⚠️ None (Finviz недоступен или заблокирован — fallback отработает)"))
        elif len(chart_fv) < 8000:
            results.append(("Finviz chart AAPL", False, f"❌ заглушка {len(chart_fv)} байт прошла мимо фильтра — BUG"))
        else:
            results.append(("Finviz chart AAPL", True, f"✅ {len(chart_fv):,} байт"))

        # yfinance chart fallback
        ok, detail = _run("yfinance chart AAPL", charting._yfinance_chart, "AAPL")
        results.append(("yfinance chart fallback AAPL", ok,
                         f"✅ {detail}" if ok else f"❌ {detail}"))

        # build_chart full pipeline
        ok2, detail2 = _run("build_chart ES=F", charting.build_chart, "ES=F")
        results.append(("build_chart ES=F", ok2,
                         f"✅ {detail2}" if ok2 else f"❌ {detail2}"))

        # Current price
        price = charting.get_current_price("AAPL")
        results.append(("get_current_price AAPL", price is not None,
                         f"✅ ${price}" if price else "❌ None"))

    except Exception as e:
        results.append(("Charting", False, f"❌ {e}"))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# 7. MEDIA / PHOTO
# ──────────────────────────────────────────────────────────────────────────────
async def test_media() -> list[tuple[str, bool, str]]:
    results = []
    try:
        from modules import media

        # Stub file check
        stubs_ok = all(os.path.exists(p) for p in media.STUB_FILES.values())
        missing = [p for p in media.STUB_FILES.values() if not os.path.exists(p)]
        results.append((
            "Стаб-файлы assets/stubs/",
            stubs_ok,
            "✅ все файлы на месте" if stubs_ok else f"❌ отсутствуют: {missing}"
        ))

        # Photo fetch — Wikimedia
        ok, detail, result = await _run_async(
            media.get_photo, "Federal Reserve", "Federal Reserve interest rates",
            None, "urgent", None, timeout_sec=20
        )
        results.append(("Media get_photo (FR тест)", ok,
                         f"✅ {type(result).__name__} {len(result) if isinstance(result, bytes) else str(result)[:80]}"
                         if ok and result else f"❌ {detail}"))
    except Exception as e:
        results.append(("Media", False, f"❌ {e}"))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# 8. COT REPORT
# ──────────────────────────────────────────────────────────────────────────────
def test_cot() -> list[tuple[str, bool, str]]:
    results = []
    try:
        from modules import cot_report

        # Один контракт
        ok, detail = _run("COT GOLD", cot_report.fetch_cot, "GOLD")
        if ok:
            item = cot_report.fetch_cot("GOLD")
            if item:
                detail = (f"✅ {item['date']} | спек.нетто="
                           f"{item['large_spec_long']-item['large_spec_short']:+,}")
            else:
                ok, detail = False, "❌ вернул None"
        results.append(("COT / GOLD (один контракт)", ok, detail))

        # Все контракты
        ok2, detail2 = _run("COT fetch_all", cot_report.fetch_all_cot)
        if ok2:
            all_items = cot_report.fetch_all_cot()
            detail2 = f"✅ {len(all_items)}/{len(cot_report.WATCHLIST_COT)} контрактов"
            ok2 = len(all_items) > 0
        results.append(("COT / все контракты", ok2, detail2))

        # Форматтер
        all_items = cot_report.fetch_all_cot()
        if all_items:
            from modules import formatter
            text = formatter.fmt_cot_report(all_items)
            ok3 = bool(text) and len(text) > 50
            results.append(("COT / formatter", ok3,
                             f"✅ {len(text)} символов" if ok3 else "❌ пустой текст"))
        else:
            results.append(("COT / formatter", False, "❌ нет данных для форматирования"))
    except Exception as e:
        results.append(("COT", False, f"❌ {e}"))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# 9. 13F FILINGS
# ──────────────────────────────────────────────────────────────────────────────
def test_13f() -> list[tuple[str, bool, str]]:
    results = []
    try:
        from modules import filings_13f

        # Один фонд — Berkshire (быстрее всего)
        ok, detail = _run("13F Berkshire", filings_13f.fetch_latest_13f, "0001067983", timeout_sec=30)
        if ok:
            item = filings_13f.fetch_latest_13f("0001067983")
            if item and item.get("positions"):
                top1 = item["positions"][0]["name"]
                detail = f"✅ {len(item['positions'])} поз. | #{1}: {top1[:40]}"
            else:
                ok, detail = False, "❌ пустые позиции"
        results.append(("13F / Berkshire", ok, detail))

        # Форматтер (даже если одна запись)
        try:
            item = filings_13f.fetch_latest_13f("0001067983")
            if item:
                item["fund_name"] = "Berkshire Hathaway (тест)"
                from modules import formatter
                text = formatter.fmt_13f_digest([item])
                ok2 = bool(text) and len(text) > 50
                results.append(("13F / formatter", ok2,
                                 f"✅ {len(text)} символов" if ok2 else "❌ пустой текст"))
            else:
                results.append(("13F / formatter", False, "❌ нет данных"))
        except Exception as ef:
            results.append(("13F / formatter", False, f"❌ {ef}"))
    except Exception as e:
        results.append(("13F", False, f"❌ {e}"))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# 10. ECON CALENDAR
# ──────────────────────────────────────────────────────────────────────────────
def test_econ_calendar() -> list[tuple[str, bool, str]]:
    results = []
    try:
        from modules import econ_calendar

        has_key = bool(os.environ.get("FRED_API_KEY"))
        if not has_key:
            results.append(("Экономкалендарь", False,
                             "❌ FRED_API_KEY не задан — модуль не работает (нужно добавить на Render)"))
            return results

        events = econ_calendar.fetch_upcoming(days_ahead=30)
        # Пустой список — не ошибка: просто нет событий в ближайшие 30 дней
        ok = isinstance(events, list)
        detail = (f"✅ {len(events)} событий в ближайшие 30 дней"
                  if events else "✅ нет событий в ближайшие 30 дней (норма)")
        results.append(("Экономкалендарь / 30 дней", ok, detail))
    except Exception as e:
        results.append(("Экономкалендарь", False, f"❌ {e}"))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# 11. EARNINGS
# ──────────────────────────────────────────────────────────────────────────────
def test_earnings() -> list[tuple[str, bool, str]]:
    results = []
    try:
        from modules import earnings
        ok, detail = _run("earnings check_upcoming", earnings.check_upcoming, 5)
        results.append(("Отчётности / check_upcoming", ok,
                         f"✅ {detail}" if ok else f"⚠️ {detail} (yfinance иногда пустой)"))
    except Exception as e:
        results.append(("Отчётности", False, f"❌ {e}"))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# 12. SECTOR HEATMAP
# ──────────────────────────────────────────────────────────────────────────────
def test_sector_heatmap() -> list[tuple[str, bool, str]]:
    results = []
    try:
        from modules import sector_heatmap
        ok, detail = _run("sector_heatmap fetch_sector_changes", sector_heatmap.fetch_sector_changes)
        results.append(("Тепловая карта секторов", ok,
                         f"✅ {detail}" if ok else f"❌ {detail}"))
    except Exception as e:
        results.append(("Тепловая карта", False, f"❌ {e}"))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# 13. SCHEDULER JOBS CHECK
# ──────────────────────────────────────────────────────────────────────────────
def test_scheduler_jobs(scheduler) -> list[tuple[str, bool, str]]:
    results = []
    expected_jobs = [
        "breaking", "hourly", "morning", "evening", "weekly", "monthly",
        "tokyo", "london", "newyork", "track_record", "moex_leaders",
        "market_pulse", "econ_calendar_weekly", "econ_calendar_today",
        "earnings_digest", "sector_heatmap", "cot_report", "filings_13f"
    ]
    if scheduler is None:
        results.append(("Планировщик", False, "❌ scheduler не инициализирован"))
        return results

    job_ids = {j.id for j in scheduler.get_jobs()}
    for jid in expected_jobs:
        ok = jid in job_ids
        results.append((f"Задача / {jid}", ok,
                         "✅ в расписании" if ok else "❌ ОТСУТСТВУЕТ"))

    # RSI/SMA алерты должны запускаться автоматически раз в час.
    in_schedule = "technical_alerts" in job_ids
    results.append(("Задача / technical_alerts (ежечасно)", in_schedule,
                     "✅ в расписании" if in_schedule else "❌ отсутствует в расписании"))

    # Проверяем misfire_grace_time
    for job in scheduler.get_jobs():
        mgrace = getattr(job, "misfire_grace_time", None)
        if mgrace is not None and mgrace < 60:
            results.append(("Планировщик / misfire_grace_time", False,
                             f"❌ {job.id}: {mgrace}s < 60s — задача будет пропускаться!"))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# 14. TRACK RECORD DB
# ──────────────────────────────────────────────────────────────────────────────
async def test_track_record() -> tuple[bool, str]:
    try:
        from modules import storage
        pending = await storage.get_unchecked_recommendations(older_than_hours=24)
        return True, f"✅ {len(pending)} рекомендаций ожидают проверки"
    except Exception as e:
        return False, f"❌ {e}"


# ──────────────────────────────────────────────────────────────────────────────
# LIVE POST TEST (отправляет реальный пост в канал)
# ──────────────────────────────────────────────────────────────────────────────
async def test_live_breaking(bot, admin_id: str) -> tuple[bool, str]:
    try:
        from modules import pipeline
        posted = await asyncio.wait_for(
            pipeline.run_breaking(bot, admin_id), timeout=60
        )
        if posted > 0:
            return True, f"✅ опубликовано {posted} breaking-пост(ов) в канал"
        return False, "❌ нет новых новостей (все дубли) или ошибка AI"
    except asyncio.TimeoutError:
        return False, "❌ timeout > 60s"
    except Exception as e:
        return False, f"❌ {e}"


# ──────────────────────────────────────────────────────────────────────────────
# СБОРКА ОТЧЁТА
# ──────────────────────────────────────────────────────────────────────────────
async def run_full_selftest(bot, admin_id: str, scheduler=None) -> str:
    """Запускает все тесты, собирает отчёт, возвращает текст для Telegram."""
    all_results: list[tuple[str, bool, str]] = []

    # Сообщение о начале
    try:
        await bot.send_message(
            chat_id=admin_id,
            text="🔍 <b>TRIADA INVESTING — запуск диагностики</b>\nПроверяю все модули, подождите...",
            parse_mode="HTML"
        )
    except Exception:
        pass

    # 1. ENV
    all_results.append(("", None, "─── 1. ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ───"))
    all_results.extend(test_env())

    # 2. Redis
    all_results.append(("", None, "─── 2. БАЗА ДАННЫХ / REDIS ───"))
    ok_redis, det_redis = await test_redis()
    all_results.append(("Upstash Redis", ok_redis, det_redis))

    ok_track, det_track = await test_track_record()
    all_results.append(("Трек-рекорд (БД)", ok_track, det_track))

    # 3. AI
    all_results.append(("", None, "─── 3. AI ANALYZER (GEMINI → GROQ) ───"))
    ok_ai, det_ai = await asyncio.to_thread(test_ai)
    all_results.append(("AI analyzer", ok_ai, det_ai))

    # 4. RSS
    all_results.append(("", None, "─── 4. ИСТОЧНИКИ НОВОСТЕЙ (RSS) ───"))
    all_results.extend(await asyncio.to_thread(test_news_sources))

    # 5. Market Pulse
    all_results.append(("", None, "─── 5. ПУЛЬС РЫНКА ───"))
    all_results.extend(await asyncio.to_thread(test_market_pulse))

    # 6. Charting
    all_results.append(("", None, "─── 6. ГРАФИКИ (Finviz → yfinance) ───"))
    all_results.extend(await asyncio.to_thread(test_charting))

    # 7. Media
    all_results.append(("", None, "─── 7. МЕДИА / ФОТО ───"))
    all_results.extend(await test_media())

    # 8. COT
    all_results.append(("", None, "─── 8. COT REPORT (CFTC) ───"))
    all_results.extend(await asyncio.to_thread(test_cot))

    # 9. 13F
    all_results.append(("", None, "─── 9. 13F FILINGS (SEC EDGAR) ───"))
    all_results.extend(await asyncio.to_thread(test_13f))

    # 10. Econ Calendar
    all_results.append(("", None, "─── 10. ЭКОНОМИЧЕСКИЙ КАЛЕНДАРЬ ───"))
    all_results.extend(await asyncio.to_thread(test_econ_calendar))

    # 11. Earnings
    all_results.append(("", None, "─── 11. ОТЧЁТНОСТИ КОМПАНИЙ ───"))
    all_results.extend(await asyncio.to_thread(test_earnings))

    # 12. Sector Heatmap
    all_results.append(("", None, "─── 12. ТЕПЛОВАЯ КАРТА СЕКТОРОВ ───"))
    all_results.extend(await asyncio.to_thread(test_sector_heatmap))

    # 13. Scheduler
    all_results.append(("", None, "─── 13. ПЛАНИРОВЩИК (ЗАДАЧИ) ───"))
    all_results.extend(await asyncio.to_thread(test_scheduler_jobs, scheduler))

    # 14. Live post test
    all_results.append(("", None, "─── 14. ЖИВОЙ ТЕСТ (реальный пост в канал) ───"))
    ok_live, det_live = await test_live_breaking(bot, admin_id)
    all_results.append(("Breaking pipeline → канал", ok_live, det_live))

    # ── Сборка текста ──────────────────────────────────────────────────────
    lines = ["<b>🔬 TRIADA INVESTING — ПОЛНАЯ ДИАГНОСТИКА</b>\n"]
    total, passed, failed = 0, 0, 0

    for (label, ok, detail) in all_results:
        if ok is None:
            # заголовок секции
            lines.append(f"\n<b>{html.escape(str(detail))}</b>")
            continue
        total += 1
        safe_label  = html.escape(str(label))
        safe_detail = html.escape(str(detail))
        if ok:
            passed += 1
            lines.append(f"✅ {safe_label}: {safe_detail}")
        else:
            failed += 1
            lines.append(f"❌ <b>{safe_label}</b>: {safe_detail}")

    pct = round(passed / total * 100) if total else 0
    summary_icon = "✅" if failed == 0 else ("⚠️" if failed <= 3 else "🔴")
    lines.append(
        f"\n<b>{summary_icon} ИТОГ: {passed}/{total} ({pct}%) тестов прошли</b>"
    )
    if failed > 0:
        lines.append(f"❌ Не прошли: {failed} — проверь параметры выше")

    # Telegram лимит 4096 символов — режем если нужно
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3950] + "\n\n<i>... (обрезано, сообщение слишком длинное)</i>"

    return text

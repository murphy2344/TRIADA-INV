import html
from datetime import datetime, timedelta
import pytz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

MSK = pytz.timezone("Europe/Moscow")

IMPACT_MAP = {
    "low":    "🟢 Низкое",
    "medium": "🟡 Среднее",
    "high":   "🔴 Высокое",
}

REC_MAP = {
    "long":    "Лонг",
    "short":   "Шорт",
    "neutral": "Нейтрально",
}


def _e(text) -> str:
    if isinstance(text, list):
        text = ", ".join(str(x) for x in text)
    return html.escape(str(text or ""))


def _impact(a: dict) -> str:
    lvl = IMPACT_MAP.get(a.get("impact_level", ""), a.get("impact_level", ""))
    detail = _e(a.get("impact_text", ""))
    return f"{lvl} — {detail}" if detail else lvl


def _rec(a: dict) -> str:
    r = REC_MAP.get(a.get("recommendation", ""), a.get("recommendation", ""))
    text = _e(a.get("recommendation_text", ""))
    base = f"{r} — {text}" if text else r

    critic_result = a.get("_critic")
    if not critic_result:
        return base

    if critic_result.get("agree"):
        return base

    critic_note = _e(critic_result.get("critic_note", ""))
    if not critic_note:
        return base
    return (
        f"{base}\n\n"
        f"<b>ОДНАКО</b> — {critic_note}"
    )


def _chip_line(chip_data: dict | None) -> str:
    """Строка-чип в стиле Apple Stocks: TICKER  цена  ±%."""
    if not chip_data:
        return ""
    ticker = _e(chip_data.get("ticker", ""))
    last = chip_data.get("last")
    pct = chip_data.get("change_pct")
    if last is None or pct is None:
        return ""
    sign = "+" if pct >= 0 else ""
    arrow = "▲" if pct >= 0 else "▼"
    return f"<b>{ticker}</b>  <code>{last:,.2f}</code>  {arrow} <code>{sign}{pct:.2f}%</code>\n\n"


def fmt_breaking(analysis: dict, source: str | None, url: str | None, chip_data: dict | None = None) -> str:
    assets = analysis.get("affected_assets", [])
    asset_lines = "\n".join(
        f"• {_e(item)}" for item in assets
    ) or "• Нет конкретного актива"
    impact_level = analysis.get("impact_level", "low")
    impact_text = {
        "high": "🔴 ВЫСОКОЕ ВЛИЯНИЕ",
        "medium": "🟡 СРЕДНЕЕ ВЛИЯНИЕ",
        "low": "🟢 НИЗКОЕ ВЛИЯНИЕ",
    }.get(impact_level, "🟡 ВЛИЯНИЕ")
    confidence = analysis.get("confidence")
    confidence_text = (
        f"{round(float(confidence) * 100)}%" if confidence is not None else "н/д"
    )
    tags = " ".join(
        f"<code>#{_e(str(item)).replace(' ', '')}</code>" for item in assets[:5]
    )
    source_block = (
        f"<b>🏛️ Источник:</b> {_e(source or 'не указан')}"
        + (f" · <a href='{html.escape(str(url), quote=True)}'>читать</a>" if url else "")
    )
    return (
        f"{_chip_line(chip_data)}"
        f"<b>{impact_level} {impact_text}</b> | {tags}\n\n"
        f"<blockquote>"
        f"<b>📰 {_e(analysis.get('title', ''))}</b>\n\n"
        f"<b>📝 Суть:</b>\n{_e(analysis.get('summary', ''))}\n\n"
        f"<b>📊 Влияние:</b>\n{_e(analysis.get('impact_text', ''))}\n\n"
        f"<b>🎯 Активы:</b>\n{asset_lines}\n\n"
        f"<b>🔮 Сценарий:</b>\n{_e(analysis.get('scenario', ''))}\n\n"
        f"<b>💡 Рекомендация:</b>\n<code>{_e(REC_MAP.get(analysis.get('recommendation'), 'Нейтрально'))}</code>"
        f" | Горизонт: {_e(analysis.get('timeframe', 'н/д'))} | Уверенность: {confidence_text}\n\n"
        f"<b>⚠️ Риск:</b>\n{_e(analysis.get('risk', 'Не указан'))}"
        f"</blockquote>\n\n"
        f"{source_block}\n"
        f"<b>⏱️ Опубликовано:</b> {datetime.now(pytz.UTC):%H:%M} UTC "
        f"({datetime.now(MSK):%H:%M} МСК)\n\n"
        f"<i>⚠️ Не является инвестиционной рекомендацией.</i>"
    )


def breaking_keyboard(analysis: dict, source_url: str | None) -> InlineKeyboardMarkup | None:
    ticker = analysis.get("ticker")
    rows = []
    if ticker:
        rows.append([InlineKeyboardButton("📈 График", callback_data=f"chart_{ticker}")])
    if source_url:
        rows[0:0] = [[InlineKeyboardButton("📰 Источник", url=source_url)]]
    rows.append([InlineKeyboardButton("📊 Трек-рекорд", callback_data="status")])
    return InlineKeyboardMarkup(rows) if rows else None


def fmt_hourly_header(now: datetime = None) -> str:
    if not now:
        now = datetime.now(MSK)
    prev_h = now.replace(minute=0, second=0, microsecond=0)
    start = (prev_h - timedelta(hours=1)).strftime("%H:00")
    end = prev_h.strftime("%H:00")
    return (
        f"<b>НОВОСТИ ЗА ЧАС</b>\n\n"
        f"<b>Новости за {start}–{end} МСК</b>\n"
        f"Главные события последнего часа на финансовых рынках.\n\n"
        f"#ДайджестЧас #Рынок #Инвестиции"
    )


def fmt_hourly_body(analyses: list) -> str:
    body = "<blockquote expandable>"
    for a in analyses[:4]:
        rec = REC_MAP.get(a.get("recommendation", ""), a.get("recommendation", ""))
        body += (
            f"— <b>{_e(a.get('title', ''))}</b>\n"
            f"Суть: {_e(a.get('summary', '')[:200])}\n"
            f"Влияние: {_impact(a)}\n"
            f"Идея: {rec}\n\n"
        )
    sources = "\n".join(
        f"• <a href='{a.get('_url', '#')}'>{_e(a.get('_source', ''))}</a>"
        for a in analyses[:4]
    )
    body += f"</blockquote>\n\nИсточники:\n{sources}"
    return body


def fmt_morning(analyses: list, date_str: str, fng: str = "") -> tuple[str, str]:
    header = f"<b>ГЛАВНЫЕ СОБЫТИЯ НОЧИ | {date_str} | Москва</b>"
    if fng:
        header += f"\n\n{fng}"
    header += "\n\n#УтренниОбзор #Рынок #Инвестиции"
    body = "<blockquote expandable>"
    for a in analyses[:4]:
        body += (
            f"• <b>{_e(a.get('title', ''))}</b>\n"
            f"{_e(a.get('summary', '')[:250])}\n"
            f"Для рынка сегодня: {_e(a.get('scenario', ''))}\n\n"
        )
    body += "</blockquote>"
    return header, body


def fmt_evening(analyses: list, date_str: str, fng: str = "") -> tuple[str, str]:
    header = f"<b>ИТОГИ ДНЯ | {date_str} | Москва</b>"
    if fng:
        header += f"\n\n{fng}"
    header += "\n\n#ИтогиДня #Рынок #Инвестиции"
    body = "<blockquote expandable>"
    for a in analyses[:4]:
        body += (
            f"• <b>{_e(a.get('title', ''))}</b>\n"
            f"{_e(a.get('summary', '')[:250])}\n"
            f"Влияние: {_impact(a)}\n\n"
        )
    if analyses:
        body += f"\n<b>Подготовка к завтрашнему дню:</b>\n{_e(analyses[0].get('scenario', ''))}"
    body += "</blockquote>"
    return header, body


def fmt_weekly(analyses: list, fng: str = "", accuracy: dict | None = None) -> tuple[str, str]:
    header = "<b>ИТОГИ НЕДЕЛИ | РЫНОК</b>\n\n#ИтогиНедели #Рынок #Инвестиции"
    body = "<blockquote expandable>"
    for a in analyses[:5]:
        body += (
            f"• <b>{_e(a.get('title', ''))}</b>\n"
            f"{_e(a.get('summary', '')[:200])}\n\n"
        )
    if fng:
        body += f"\n<b>Индекс страха и жадности:</b> {fng}"
    if accuracy and accuracy.get("total"):
        body += (
            f"\n\n<b>🎯 Точность рекомендаций за неделю:</b> "
            f"<b>{accuracy['accuracy_pct']}%</b> "
            f"({accuracy['correct']}/{accuracy['total']} верных)"
        )
    body += "</blockquote>"
    return header, body


PERIOD_LABELS = {"day": "За день", "week": "За неделю", "month": "За месяц", "year": "За год"}


def fmt_leaders(all_periods: dict) -> tuple[str, str]:
    header = "<b>ЛИДЕРЫ РОСТА И ПАДЕНИЯ | МИРОВОЙ РЫНОК</b>\n\n#МировойРынок #ЛидерыРынка #Инвестиции"
    body = "<blockquote expandable>"

    any_data = False
    for period in ("day", "week", "month", "year"):
        gainers, losers = all_periods.get(period, ([], []))
        if not gainers and not losers:
            continue
        any_data = True
        body += f"<b>{PERIOD_LABELS[period]}</b>\n"
        if gainers:
            body += "🟢 Рост:\n"
            for g in gainers:
                body += f"  {_e(g['ticker'])} ({_e(g['name'])}): +{g['change_pct']:.2f}%\n"
        if losers:
            body += "🔴 Падение:\n"
            for l in losers:
                body += f"  {_e(l['ticker'])} ({_e(l['name'])}): {l['change_pct']:.2f}%\n"
        body += "\n"

    if not any_data:
        body += "Нет данных за выбранные периоды (возможно, выходной день на бирже)."

    body += "</blockquote>\nИсточник: Yahoo Finance"
    return header, body


def fmt_monthly(analyses: list) -> tuple[str, str]:
    header = "<b>ИТОГИ МЕСЯЦА</b>\n\n#ИтогиМесяца #Рынок #Инвестиции"
    body = "<blockquote expandable><b>Главные макрособытия:</b>\n\n"
    for a in analyses[:6]:
        body += (
            f"• <b>{_e(a.get('title', ''))}</b>\n"
            f"{_e(a.get('summary', '')[:200])}\n\n"
        )
    body += "\n<b>Ключевые активы месяца:</b>\n"
    all_assets = []
    for a in analyses[:6]:
        assets = a.get("affected_assets", [])
        if isinstance(assets, list):
            all_assets.extend(assets)
    if all_assets:
        body += _e(", ".join(dict.fromkeys(all_assets))[:300])
    body += "</blockquote>"
    return header, body


def fmt_technical_alert(ticker: str, signals: list) -> str:
    lines = [f"• {_e(s['text'])}" for s in signals]
    return (
        f"<b>ТЕХНИЧЕСКИЙ СИГНАЛ — {_e(ticker)}</b>\n\n" + "\n".join(lines) +
        "\n\n<i>Не является торговой рекомендацией — технический индикатор к сведению.</i>\n\n"
        f"#ТехАлерт #{_e(ticker).replace('-', '')} #Инвестиции"
    )


def fmt_exchange_open(exchange: str, index: str, now: datetime = None) -> str:
    if not now:
        now = datetime.now(MSK)
    time_str = now.strftime("%H:%M МСК")
    return (
        f"Открылась торговая сессия: <b>{_e(exchange)}</b> ({_e(index)}) — {time_str}\n\n"
        f"#Биржа #Открытие #Рынок"
    )


def fmt_econ_calendar_weekly(releases: list) -> str:
    if not releases:
        return ""
    lines = [f"• {_e(r['name'])} — <code>{r['date'].strftime('%d.%m')}</code>" for r in releases]
    return (
        "<b>ГЛАВНЫЕ ЭКОНОМИЧЕСКИЕ СОБЫТИЯ НЕДЕЛИ</b>\n\n" + "\n".join(lines) +
        "\n\n#ЭкономКалендарь #Макро #Инвестиции"
    )


def fmt_earnings_upcoming(items: list) -> str:
    if not items:
        return ""
    lines = [f"• <b>{_e(i['ticker'])}</b> — <code>{i['date'].strftime('%d.%m')}</code>" for i in items]
    return "<b>СКОРО ОТЧЁТНОСТЬ</b>\n\n" + "\n".join(lines) + "\n\n#Отчетность #Акции #Инвестиции"


def fmt_earnings_recent(items: list) -> str:
    if not items:
        return ""
    lines = []
    for i in items:
        est = i.get("estimate")
        rep = i.get("reported")
        surprise = i.get("surprise_pct")
        est_str = f"{est:.2f}" if est is not None else "н/д"
        rep_str = f"{rep:.2f}" if rep is not None else "н/д"
        surprise_str = f" ({'+' if (surprise or 0) >= 0 else ''}{surprise:.1f}%)" if surprise is not None else ""
        lines.append(
            f"• <b>{_e(i['ticker'])}</b>: факт <code>{rep_str}</code> "
            f"vs прогноз <code>{est_str}</code>{surprise_str}"
        )
    return "<b>ОТЧЁТНОСТЬ: ФАКТ ПРОТИВ ПРОГНОЗА</b>\n\n" + "\n".join(lines) + "\n\n#Отчетность #Акции #Инвестиции"


def fmt_sector_heatmap(changes: dict, sectors_labels: dict) -> str:
    if not changes:
        return ""
    items = sorted(changes.items(), key=lambda kv: kv[1], reverse=True)
    lines = []
    for etf, pct in items:
        name = sectors_labels.get(etf, etf)
        sign = "+" if pct >= 0 else ""
        lines.append(f"• {_e(name)}: <code>{sign}{pct:.2f}%</code>")
    return "<b>ТЕПЛОВАЯ КАРТА СЕКТОРОВ</b>\n\n" + "\n".join(lines) + "\n\n#Секторы #США #Инвестиции"


def fmt_econ_calendar_today(releases: list) -> str:
    if not releases:
        return ""
    lines = [f"• {_e(r['name'])}" for r in releases]
    return (
        "<b>СЕГОДНЯ — ВАЖНЫЕ ЭКОНОМИЧЕСКИЕ ДАННЫЕ</b>\n\n" + "\n".join(lines) +
        "\n\nОжидается повышенная волатильность.\n\n"
        "#ЭкономКалендарь #Макро #Волатильность"
    )


def fmt_track_record_result(results: list) -> str:
    """Публикует итоги проверки рекомендаций через 24 часа.
    results: list of dicts — ticker, recommendation, price_at_post, price_after, correct"""
    if not results:
        return ""

    lines = []
    for r in results:
        ticker = _e(r["ticker"])
        rec = REC_MAP.get(r["recommendation"], r["recommendation"])
        price_at = r["price_at_post"]
        price_after = r["price_after"]
        try:
            change_pct = (price_after - price_at) / price_at * 100
        except ZeroDivisionError:
            change_pct = 0.0
        sign = "+" if change_pct >= 0 else ""
        ok_icon = "✅" if r["correct"] else "❌"
        lines.append(
            f"{ok_icon} <b>{ticker}</b> — {rec}\n"
            f"Цена тогда: <code>{price_at:,.2f}</code> → сейчас: <code>{price_after:,.2f}</code> "
            f"(<code>{sign}{change_pct:.2f}%</code>)"
        )

    return (
        "<b>🎯 ПРОВЕРКА РЕКОМЕНДАЦИЙ (24 часа)</b>\n\n"
        + "\n\n".join(lines)
        + "\n\n#ТрекРекорд #Инвестиции"
    )


def fmt_cot_report(items: list) -> str:
    """COT (Commitments of Traders) — позиции крупных спекулянтов и хеджеров."""
    if not items:
        return ""

    lines = []
    for item in items:
        long_s = item.get("large_spec_long", 0)
        short_s = item.get("large_spec_short", 0)
        netto = long_s - short_s
        sentiment = "бычий настрой 🟢" if netto > 0 else "медвежий настрой 🔴"
        sign = "+" if netto >= 0 else ""

        # Берём короткое имя из названия контракта (до первой запятой/тире)
        contract_full = item.get("contract", item.get("ticker", ""))
        short_name = contract_full.split(" - ")[0].split(",")[0].strip()

        lines.append(
            f"<b>{_e(short_name)}</b>\n"
            f"Крупные спекулянты нетто: <code>{sign}{netto:,}</code> контрактов — {sentiment}\n"
            f"(лонг: <code>{long_s:,}</code> / шорт: <code>{short_s:,}</code>)"
        )

    date_str = items[0].get("date", "") if items else ""
    header = f"<b>ПОЗИЦИИ КРУПНЫХ ИГРОКОВ (COT)</b>"
    if date_str:
        header += f"\n<i>Отчёт CFTC за {date_str}</i>"

    return (
        header + "\n\n"
        + "\n\n".join(lines)
        + "\n\n<i>Источник: CFTC Commitments of Traders (Legacy Combined)</i>\n\n"
        "#COT #КрупныеИгроки #Фьючерсы #Инвестиции"
    )


def fmt_13f_digest(items: list) -> str:
    """13F Filings — что покупают крупные институциональные фонды."""
    if not items:
        return ""

    sections = []
    for item in items:
        fund_name = _e(item.get("fund_name", "Неизвестный фонд"))
        positions = item.get("positions", [])
        period = _e(item.get("report_period", ""))

        pos_lines = []
        for pos in positions[:5]:
            val = pos.get("value", 0)
            val_str = f"${val * 1000:,.0f}" if val else "н/д"
            pos_lines.append(f"• {_e(pos['name'])}: <code>{val_str}</code>")

        section = f"<b>{fund_name}</b>"
        if period:
            section += f" <i>({period})</i>"
        if pos_lines:
            section += "\nТоп-5 позиций:\n" + "\n".join(pos_lines)
        else:
            section += "\n<i>Позиции не удалось получить</i>"

        sections.append(section)

    return (
        "<b>ЧТО ПОКУПАЮТ КРУПНЫЕ ФОНДЫ (13F)</b>\n\n"
        + "\n\n".join(sections)
        + "\n\n<i>Данные за последний поданный квартал, публикуются с задержкой "
        "до 45 дней по требованию SEC.</i>\n\n"
        "#13F #КрупныеФонды #Институционалы #Инвестиции"
    )

import html
from datetime import datetime, timedelta
import pytz

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
        return f"{base}\n\n<i>Проверено вторым мнением (Gemini) — согласен.</i>"

    critic_rec = REC_MAP.get(
        critic_result.get("critic_recommendation", ""),
        critic_result.get("critic_recommendation", ""),
    )
    critic_note = _e(critic_result.get("critic_note", ""))
    return (
        f"{base}\n\n"
        f"<i>Альтернативное мнение (Gemini): {critic_rec} — {critic_note}</i>"
    )


def fmt_breaking(analysis: dict, source: str, url: str) -> str:
    assets = _e(analysis.get("affected_assets", []))
    return (
        f"<b>СРОЧНО — РЫНОК</b>\n\n"
        f"<b>{_e(analysis.get('title', ''))}</b>\n\n"
        f"<blockquote expandable>"
        f"<b>Суть новости:</b>\n{_e(analysis.get('summary', ''))}\n\n"
        f"<b>Влияние на рынок:</b>\n{_impact(analysis)}\n\n"
        f"<b>Затронутые активы:</b> {assets}\n\n"
        f"<b>Возможный сценарий:</b>\n{_e(analysis.get('scenario', ''))}\n\n"
        f"<b>Рекомендация:</b>\n{_rec(analysis)}"
        f"</blockquote>\n\n"
        f"Источник: {_e(source)} • <a href='{url}'>читать</a>"
    )


def fmt_hourly_header(now: datetime = None) -> str:
    if not now:
        now = datetime.now(MSK)
    prev_h = now.replace(minute=0, second=0, microsecond=0)
    start = (prev_h - timedelta(hours=1)).strftime("%H:00")
    end = prev_h.strftime("%H:00")
    return (
        f"<b>НОВОСТИ ЗА ЧАС</b>\n\n"
        f"<b>Новости за {start}–{end} МСК</b>\n"
        f"Главные события последнего часа на финансовых рынках."
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
    header = "<b>ИТОГИ НЕДЕЛИ | РЫНОК</b>"
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
            f"\n\n<b>Точность рекомендаций за неделю:</b> "
            f"{accuracy['accuracy_pct']}% ({accuracy['correct']}/{accuracy['total']})"
        )
    body += "</blockquote>"
    return header, body


PERIOD_LABELS = {"day": "За день", "week": "За неделю", "month": "За месяц", "year": "За год"}


def fmt_leaders(all_periods: dict) -> tuple[str, str]:
    """all_periods: {"day": (gainers, losers), "week": (...), "month": (...), "year": (...)}"""
    header = "<b>ЛИДЕРЫ РОСТА И ПАДЕНИЯ | МОСБИРЖА</b>"
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

    body += "</blockquote>\nИсточник: MOEX ISS"
    return header, body


def fmt_monthly(analyses: list) -> tuple[str, str]:
    header = "<b>ИТОГИ МЕСЯЦА</b>"
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


def fmt_exchange_open(exchange: str, index: str, now: datetime = None) -> str:
    if not now:
        now = datetime.now(MSK)
    time_str = now.strftime("%H:%M МСК")
    return f"Открылась торговая сессия: <b>{_e(exchange)}</b> ({_e(index)}) — {time_str}"

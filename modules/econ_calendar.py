"""
Экономический календарь — через официальный бесплатный API FRED (Федеральный
резервный банк Сент-Луиса). Нужен FRED_API_KEY (бесплатно, без карты).

Curated список ключевых релизов — их release_id проверены напрямую на
сайте fred.stlouisfed.org (не выдуманы):
10  = Consumer Price Index (инфляция США)
50  = Employment Situation (рынок труда США, NFP)
53  = Gross Domestic Product (ВВП США)
101 = FOMC Press Release (решение ФРС по ставке)
"""
import logging
import datetime
import requests
from config.config import FRED_API_KEY

logger = logging.getLogger(__name__)

FRED_URL = "https://api.stlouisfed.org/fred/release/dates"
TIMEOUT = 10

CURATED_RELEASES = {
    10: "Индекс потребительских цен США (CPI)",
    50: "Рынок труда США (Employment Situation, NFP)",
    53: "ВВП США (GDP)",
    101: "Решение ФРС по ставке (FOMC)",
}


def fetch_upcoming(days_ahead: int = 14) -> list[dict]:
    """Ближайшая дата по каждому curated-релизу в пределах days_ahead дней.
    Если FRED_API_KEY не задан — возвращает пустой список (бот работает
    без календаря, не падает)."""
    if not FRED_API_KEY:
        return []

    today = datetime.date.today()
    horizon = today + datetime.timedelta(days=days_ahead)
    results = []

    for release_id, name in CURATED_RELEASES.items():
        try:
            resp = requests.get(
                FRED_URL,
                params={
                    "release_id": release_id,
                    "api_key": FRED_API_KEY,
                    "file_type": "json",
                    "sort_order": "asc",
                    "realtime_start": today.isoformat(),
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            dates = resp.json().get("release_dates", [])
            for d in dates:
                date_str = d.get("date")
                if not date_str:
                    continue
                date_obj = datetime.date.fromisoformat(date_str)
                if today <= date_obj <= horizon:
                    results.append({"name": name, "date": date_obj})
                    break  # только ближайшая дата по этому релизу
        except Exception as e:
            logger.error(f"FRED fetch error (release_id={release_id}): {e}")
            continue

    results.sort(key=lambda x: x["date"])
    return results


def get_today_releases() -> list[dict]:
    """Релизы, которые выходят СЕГОДНЯ — для дневного предупреждения."""
    today = datetime.date.today()
    upcoming = fetch_upcoming(days_ahead=1)
    return [r for r in upcoming if r["date"] == today]

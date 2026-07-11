"""
Лидеры роста/падения акций Мосбиржи — через официальный бесплатный
MOEX ISS API (iss.moex.com), без ключа, без ограничений на такой объём
запросов.

День — 1 запрос к текущему снимку доски TQBR (там уже готовое поле CHANGE).
Неделя/месяц/год — текущий снимок + 1 исторический снимок на нужную дату
назад (тоже одним запросом на весь список бумаг, не по одной).
"""
import logging
import datetime
import requests

logger = logging.getLogger(__name__)

BASE = "https://iss.moex.com/iss"
BOARD = "TQBR"
TIMEOUT = 15

PERIOD_DAYS = {"week": 7, "month": 30, "year": 365}


def _rows_to_dicts(block: dict) -> list[dict]:
    """MOEX ISS отдаёт {"columns": [...], "data": [[...], ...]} —
    превращаем в список словарей по колонкам."""
    if not block:
        return []
    columns = block.get("columns", [])
    data = block.get("data", [])
    return [dict(zip(columns, row)) for row in data]


def fetch_current_snapshot() -> dict:
    """Текущие данные по всем акциям доски TQBR: тикер -> {name, last, change_pct, value}."""
    url = f"{BASE}/engines/stock/markets/shares/boards/{BOARD}/securities.json"
    params = {
        "iss.meta": "off",
        "securities.columns": "SECID,SHORTNAME",
        "marketdata.columns": "SECID,LAST,CHANGE,VALTODAY",
    }
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"MOEX snapshot error: {e}")
        return {}

    names = {r["SECID"]: r.get("SHORTNAME", r["SECID"]) for r in _rows_to_dicts(data.get("securities"))}
    result = {}
    for r in _rows_to_dicts(data.get("marketdata")):
        secid = r.get("SECID")
        last = r.get("LAST")
        if not secid or last is None:
            continue
        result[secid] = {
            "name": names.get(secid, secid),
            "last": last,
            "change_pct": r.get("CHANGE"),
            "value": r.get("VALTODAY") or 0,
        }
    return result


def fetch_historical_close(date_str: str) -> dict:
    """Цены закрытия на конкретную дату: тикер -> close. Пустой словарь,
    если в этот день торгов не было (выходной/праздник) — вызывающий код
    сам отвечает за поиск ближайшего торгового дня."""
    url = f"{BASE}/history/engines/stock/markets/shares/boards/{BOARD}/securities.json"
    params = {
        "iss.meta": "off",
        "date": date_str,
        "history.columns": "SECID,CLOSE",
    }
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"MOEX history error ({date_str}): {e}")
        return {}

    result = {}
    for r in _rows_to_dicts(data.get("history")):
        secid = r.get("SECID")
        close = r.get("CLOSE")
        if secid and close is not None:
            result[secid] = close
    return result


def _find_trading_day_close(target_date: datetime.date, max_lookback: int = 7) -> dict:
    """Ищет ближайший ТОРГОВЫЙ день не позже target_date (на случай, если
    попали на выходной/праздник) — идёт назад до max_lookback дней."""
    for offset in range(max_lookback):
        d = target_date - datetime.timedelta(days=offset)
        closes = fetch_historical_close(d.isoformat())
        if closes:
            return closes
    return {}


def _split_gainers_losers(changes: list, top_n: int) -> tuple[list, list]:
    """Строго разделяет по знаку изменения — растущая бумага никогда не
    попадёт в список падения, даже если бумаг мало (top_n близко к общему
    числу). Раньше эта функция брала просто 'верхние N' и 'нижние N', и при
    малой выборке в 'падение' мог попасть актив с положительным изменением."""
    positive = [c for c in changes if c["change_pct"] is not None and c["change_pct"] > 0]
    negative = [c for c in changes if c["change_pct"] is not None and c["change_pct"] < 0]
    positive.sort(key=lambda x: x["change_pct"], reverse=True)
    negative.sort(key=lambda x: x["change_pct"])
    return positive[:top_n], negative[:top_n]


def _compute_period_leaders(current: dict, past_closes: dict, top_n: int) -> tuple[list, list]:
    changes = []
    for secid, info in current.items():
        past = past_closes.get(secid)
        if not past or past == 0:
            continue
        pct = (info["last"] - past) / past * 100
        changes.append({"ticker": secid, "name": info["name"], "change_pct": pct})

    return _split_gainers_losers(changes, top_n)


def get_daily_leaders(top_n: int = 5) -> tuple[list, list]:
    current = fetch_current_snapshot()
    changes = [
        {"ticker": secid, "name": info["name"], "change_pct": info["change_pct"]}
        for secid, info in current.items()
        if info.get("change_pct") is not None
    ]
    return _split_gainers_losers(changes, top_n)


def get_period_leaders(period: str, top_n: int = 5) -> tuple[list, list]:
    """period: 'week' | 'month' | 'year'"""
    days_back = PERIOD_DAYS.get(period)
    if not days_back:
        return [], []

    current = fetch_current_snapshot()
    if not current:
        return [], []

    target_date = datetime.date.today() - datetime.timedelta(days=days_back)
    past_closes = _find_trading_day_close(target_date)
    if not past_closes:
        logger.warning(f"MOEX: не удалось найти торговый день для периода {period}")
        return [], []

    return _compute_period_leaders(current, past_closes, top_n)


def get_all_periods_leaders(top_n: int = 5) -> dict:
    """Собирает лидеров по всем 4 периодам за минимум запросов (текущий
    снимок переиспользуется для всех периодов, не запрашивается заново)."""
    result = {}
    day_g, day_l = get_daily_leaders(top_n)
    result["day"] = (day_g, day_l)

    current = fetch_current_snapshot()
    for period, days_back in PERIOD_DAYS.items():
        target_date = datetime.date.today() - datetime.timedelta(days=days_back)
        past_closes = _find_trading_day_close(target_date)
        if past_closes and current:
            result[period] = _compute_period_leaders(current, past_closes, top_n)
        else:
            result[period] = ([], [])
    return result

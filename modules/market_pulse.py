"""
Пульс рынка для закреплённого сообщения.

USD/RUB — через Yahoo Finance (yfinance, USDRUB=X): даёт актуальный курс
в любое время суток, а не только во время торгов на MOEX.

IMOEX — через официальный бесплатный MOEX ISS API: единственный источник
индекса Мосбиржи в реальном времени, ключ не нужен.
"""
import logging
import datetime
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

TIMEOUT = 10
IMOEX_URL = "https://iss.moex.com/iss/engines/stock/markets/index/boards/SNDX/securities/IMOEX.json"


def _first_row(block: dict) -> dict | None:
    if not block:
        return None
    columns = block.get("columns", [])
    data = block.get("data", [])
    if not data:
        return None
    return dict(zip(columns, data[0]))


def fetch_usd_rub() -> float | None:
    """Yahoo Finance USDRUB=X — актуальный курс вне зависимости от расписания MOEX."""
    try:
        hist = yf.Ticker("USDRUB=X").history(period="1d", interval="5m")
        if hist is not None and not hist.empty:
            price = float(hist["Close"].iloc[-1])
            if price > 0:
                return round(price, 2)
        return None
    except Exception as e:
        logger.error(f"USD/RUB (yfinance) fetch error: {e}")
        return None


def fetch_imoex() -> dict | None:
    """MOEX ISS — индекс Мосбиржи IMOEX."""
    try:
        resp = requests.get(
            IMOEX_URL,
            params={"iss.meta": "off", "marketdata.columns": "SECID,CURRENTVALUE,LASTTOPREVPRICE"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        row = _first_row(resp.json().get("marketdata"))
        if not row or row.get("CURRENTVALUE") is None:
            return None
        return {"value": row["CURRENTVALUE"], "change_pct": row.get("LASTTOPREVPRICE")}
    except Exception as e:
        logger.error(f"IMOEX fetch error: {e}")
        return None


def build_pulse_text() -> str:
    """Текст закреплённого сообщения. Если какие-то данные недоступны —
    просто не включаем их в строку, не выдумываем цифры."""
    usd_rub = fetch_usd_rub()
    imoex = fetch_imoex()

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    parts = []
    if usd_rub is not None:
        parts.append(f"USD/RUB <code>{usd_rub:,.2f}</code>")
    if imoex is not None:
        pct = imoex.get("change_pct")
        sign = "+" if (pct or 0) >= 0 else ""
        pct_str = f" ({sign}{pct:.2f}%)" if pct is not None else ""
        parts.append(f"IMOEX <code>{imoex['value']:,.2f}</code>{pct_str}")

    if not parts:
        return "📌 Пульс рынка временно недоступен — обновим в следующий раз."

    return "📌 <b>Пульс рынка</b> · " + " · ".join(parts) + f"\nОбновлено {now.strftime('%H:%M МСК')}"

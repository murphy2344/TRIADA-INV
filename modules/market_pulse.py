"""Compact global market pulse for the pinned Telegram message."""
import datetime
import logging

import requests

logger = logging.getLogger(__name__)

IMOEX_MARKETDATA_URL = (
    "https://iss.moex.com/iss/engines/stock/markets/index"
    "/boards/SNDX/securities/IMOEX.json"
)
MOEX_TIMEOUT = 10


def _moex_first_row(block: dict) -> dict | None:
    if not block or not block.get("data"):
        return None
    return dict(zip(block.get("columns", []), block["data"][0]))


def fetch_imoex() -> dict | None:
    try:
        response = requests.get(
            IMOEX_MARKETDATA_URL,
            params={
                "iss.meta": "off",
                "marketdata.columns": "SECID,CURRENTVALUE,LASTTOPREVPRICE",
                "securities.columns": "SECID,PREVPRICE",
            },
            timeout=MOEX_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        market = _moex_first_row(payload.get("marketdata"))
        securities = _moex_first_row(payload.get("securities"))
        if market and market.get("CURRENTVALUE") is not None:
            return {
                "value": float(market["CURRENTVALUE"]),
                "change_pct": market.get("LASTTOPREVPRICE"),
                "is_closed": False,
            }
        if securities and securities.get("PREVPRICE") is not None:
            return {
                "value": float(securities["PREVPRICE"]),
                "change_pct": None,
                "is_closed": True,
            }
    except Exception as exc:
        logger.error("IMOEX fetch error: %s", exc)
    return None


def _download_quote(ticker: str) -> dict | None:
    try:
        import yfinance as yf

        data = yf.download(
            ticker,
            period="5d",
            interval="1d",
            progress=False,
            auto_adjust=True,
            multi_level_index=False,
        )
        if data is None or data.empty or "Close" not in data.columns:
            return None
        closes = data["Close"].dropna()
        if len(closes) < 1:
            return None
        current = float(closes.iloc[-1])
        previous = float(closes.iloc[-2]) if len(closes) > 1 else current
        change = ((current - previous) / previous * 100) if previous else 0.0
        return {"value": current, "change_pct": change}
    except Exception as exc:
        logger.warning("Global quote %s failed: %s", ticker, exc)
        return None


def fetch_usd_rub() -> float | None:
    quote = _download_quote("USDRUB=X")
    return round(quote["value"], 2) if quote else None


def _emoji(change: float | None) -> str:
    if change is None:
        return "🟡"
    if change > 0.5:
        return "🟢"
    if change < -0.5:
        return "🔴"
    return "🟡"


def _format_quote(label: str, quote: dict | None, decimals: int = 2) -> str:
    if not quote:
        return f"🟡<b>{label}</b> n/d"
    change = quote.get("change_pct")
    change_text = "n/d" if change is None else f"{change:+.2f}%"
    return (
        f"{_emoji(change)}<b>{label}</b> "
        f"<code>{quote['value']:,.{decimals}f}</code> "
        f"<code>{change_text}</code>"
    )


def build_pulse_text() -> str:
    """Three compact lines; unavailable sources are shown as n/d, never invented."""
    tickers = {
        "SPX": "^GSPC",
        "NDX": "^IXIC",
        "VIX": "^VIX",
        "DXY": "DX-Y.NYB",
        "10Y": "^TNX",
        "WTI": "CL=F",
        "Gold": "GC=F",
    }
    quotes = {label: _download_quote(ticker) for label, ticker in tickers.items()}
    # Yahoo reports ^TNX in percentage points*10.
    if quotes["10Y"]:
        quotes["10Y"]["value"] /= 10

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    return (
        f"<b>📊 ПУЛЬС РЫНКА</b> <code>{now:%H:%M} МСК</code>\n\n"
        f"{_format_quote('SPX', quotes['SPX'], 2)} | "
        f"{_format_quote('NDX', quotes['NDX'], 2)}\n"
        f"{_format_quote('VIX', quotes['VIX'], 2)} | "
        f"{_format_quote('DXY', quotes['DXY'], 2)} | "
        f"{_format_quote('10Y', quotes['10Y'], 2)}\n"
        f"{_format_quote('WTI', quotes['WTI'], 2)} | "
        f"{_format_quote('Gold', quotes['Gold'], 2)}"
    )
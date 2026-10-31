"""Compact global market pulse for the pinned Telegram message."""
import datetime
import logging

import requests

logger = logging.getLogger(__name__)


def _download_quote(ticker: str) -> dict | None:
    try:
        from modules import charting

        data = charting._fetch_yfinance_history(ticker, "5d", "1d")
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
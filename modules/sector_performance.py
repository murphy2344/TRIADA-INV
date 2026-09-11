"""Sector performance tracker - which sectors are leading today.

Tracks major US sector ETFs:
- XLK (Technology)
- XLF (Financials)
- XLE (Energy)
- XLV (Healthcare)
- XLI (Industrials)
- XLP (Consumer Staples)
- XLY (Consumer Discretionary)
- XLU (Utilities)
- XLRE (Real Estate)
- XLC (Communication Services)
- XLB (Materials)
"""
import asyncio
import logging
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)

SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Healthcare",
    "XLI": "Industrials",
    "XLP": "Consumer Staples",
    "XLY": "Consumer Discretionary",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
    "XLB": "Materials",
}


async def _fetch_sector_performance(symbol: str) -> dict[str, Any] | None:
    """Fetch performance for a sector ETF."""
    try:
        ticker = await asyncio.to_thread(yf.Ticker, symbol)
        hist = await asyncio.to_thread(lambda: ticker.history(period="5d"))

        if hist.empty or len(hist) < 2:
            return None

        current_price = hist["Close"].iloc[-1]
        prev_close = hist["Close"].iloc[-2]
        change_pct = ((current_price - prev_close) / prev_close) * 100

        # Week performance (5 days ago)
        if len(hist) >= 5:
            week_ago_price = hist["Close"].iloc[0]
            week_change_pct = ((current_price - week_ago_price) / week_ago_price) * 100
        else:
            week_change_pct = None

        return {
            "symbol": symbol,
            "name": SECTOR_ETFS.get(symbol, symbol),
            "price": current_price,
            "change_pct": change_pct,
            "week_change_pct": week_change_pct,
        }
    except Exception as e:
        logger.error(f"Failed to fetch sector performance for {symbol}: {e}")
        return None


async def fetch_all_sectors() -> list[dict[str, Any]]:
    """Fetch performance for all sector ETFs."""
    tasks = [_fetch_sector_performance(symbol) for symbol in SECTOR_ETFS.keys()]
    results = await asyncio.gather(*tasks)

    # Filter out None results and sort by daily performance
    valid_results = [r for r in results if r]
    valid_results.sort(key=lambda x: x["change_pct"], reverse=True)

    return valid_results


def format_sector_performance(sectors: list[dict[str, Any]]) -> str:
    """Format sector performance into readable message."""
    from datetime import datetime

    if not sectors:
        return ""

    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M UTC")

    lines = [
        f"📊 <b>SECTOR PERFORMANCE</b> — {timestamp}\n",
        "<b>Сегодня:</b>\n"
    ]

    for sector in sectors:
        change = sector["change_pct"]

        # Emoji based on performance
        if change >= 1.5:
            emoji = "🚀"
        elif change >= 0.5:
            emoji = "🟢"
        elif change >= 0:
            emoji = "⬆️"
        elif change >= -0.5:
            emoji = "⬇️"
        elif change >= -1.5:
            emoji = "🔴"
        else:
            emoji = "💥"

        week_str = ""
        if sector.get("week_change_pct") is not None:
            week_change = sector["week_change_pct"]
            week_str = f" | Неделя: {week_change:+.1f}%"

        lines.append(
            f"{emoji} <b>{sector['name']}</b> ({sector['symbol']}): "
            f"{change:+.2f}%{week_str}"
        )

    # Add market rotation insight
    lines.append("\n<b>🔄 Ротация секторов:</b>")

    top_3 = sectors[:3]
    bottom_3 = sectors[-3:]

    if top_3:
        top_names = ", ".join([s['name'] for s in top_3])
        lines.append(f"💪 Сильные: {top_names}")

    if bottom_3:
        bottom_names = ", ".join([s['name'] for s in bottom_3])
        lines.append(f"📉 Слабые: {bottom_names}")

    # Risk-on vs Risk-off analysis
    lines.append("\n<b>📈 Настроение:</b>")

    # Calculate average for cyclical vs defensive
    cyclical = ["XLY", "XLF", "XLI", "XLK", "XLE"]  # Cyclical sectors
    defensive = ["XLP", "XLU", "XLV"]  # Defensive sectors

    cyclical_avg = sum([s["change_pct"] for s in sectors if s["symbol"] in cyclical]) / len(cyclical)
    defensive_avg = sum([s["change_pct"] for s in sectors if s["symbol"] in defensive]) / len(defensive)

    if cyclical_avg > defensive_avg + 0.3:
        lines.append("🟢 <b>Risk-ON</b> — циклические секторы растут")
    elif defensive_avg > cyclical_avg + 0.3:
        lines.append("🔴 <b>Risk-OFF</b> — защитные секторы растут")
    else:
        lines.append("😐 <b>Смешанное</b> настроение рынка")

    return "\n".join(lines)

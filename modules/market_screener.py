"""Market screener - find trading opportunities.

Scans for:
- Breakouts (price breaking resistance)
- Unusual volume
- Technical signals (RSI, MACD, Golden Cross)
- Top gainers/losers
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

# Popular tickers to scan
SCAN_UNIVERSE = [
    # Mega caps
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B",
    # Large caps tech
    "AMD", "INTC", "AVGO", "ORCL", "CRM", "ADBE", "CSCO", "QCOM",
    # Large caps other sectors
    "JPM", "V", "MA", "WMT", "UNH", "JNJ", "PG", "XOM", "CVX",
    # Growth stocks
    "NFLX", "DIS", "BABA", "NIO", "PLTR", "RBLX", "SNOW",
    # ETFs
    "SPY", "QQQ", "IWM", "DIA",
    # Crypto
    "BTC-USD", "ETH-USD",
]


async def _fetch_ticker_technical(symbol: str, period: str = "3mo") -> dict[str, Any] | None:
    """Fetch technical data for a ticker."""
    try:
        ticker = await asyncio.to_thread(yf.Ticker, symbol)
        hist = await asyncio.to_thread(
            lambda: ticker.history(period=period, interval="1d")
        )

        if hist.empty or len(hist) < 20:
            return None

        current_price = hist["Close"].iloc[-1]
        prev_close = hist["Close"].iloc[-2] if len(hist) >= 2 else current_price

        # Calculate technical indicators
        close = hist["Close"]
        volume = hist["Volume"]

        # RSI (14-day)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1] if not rsi.empty else 50

        # Volume analysis
        avg_volume = volume.rolling(window=20).mean().iloc[-1]
        current_volume = volume.iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

        # Price change
        change_pct = ((current_price - prev_close) / prev_close) * 100

        # 52-week high/low
        high_52w = close.rolling(window=252).max().iloc[-1]
        low_52w = close.rolling(window=252).min().iloc[-1]
        distance_from_high = ((current_price - high_52w) / high_52w) * 100

        # Moving averages
        sma_20 = close.rolling(window=20).mean().iloc[-1]
        sma_50 = close.rolling(window=50).mean().iloc[-1] if len(close) >= 50 else None
        sma_200 = close.rolling(window=200).mean().iloc[-1] if len(close) >= 200 else None

        # Detect breakout (price above recent high)
        recent_high = close.iloc[-20:-1].max() if len(close) >= 20 else current_price
        is_breakout = current_price > recent_high * 1.01  # 1% above recent high

        return {
            "symbol": symbol,
            "price": current_price,
            "change_pct": change_pct,
            "volume": current_volume,
            "avg_volume": avg_volume,
            "volume_ratio": volume_ratio,
            "rsi": current_rsi,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "distance_from_high": distance_from_high,
            "sma_20": sma_20,
            "sma_50": sma_50,
            "sma_200": sma_200,
            "is_breakout": is_breakout,
            "recent_high": recent_high,
        }
    except Exception as e:
        logger.warning(f"Failed to fetch technical data for {symbol}: {e}")
        return None


async def scan_breakouts(min_volume_ratio: float = 1.5) -> list[dict[str, Any]]:
    """Scan for breakout opportunities."""
    logger.info("Scanning for breakouts...")

    tasks = [_fetch_ticker_technical(symbol) for symbol in SCAN_UNIVERSE]
    results = await asyncio.gather(*tasks)

    breakouts = []
    for data in results:
        if data and data["is_breakout"] and data["volume_ratio"] >= min_volume_ratio:
            breakouts.append(data)

    # Sort by volume ratio (strongest first)
    breakouts.sort(key=lambda x: x["volume_ratio"], reverse=True)
    return breakouts[:10]  # Top 10


async def scan_unusual_volume(min_ratio: float = 2.0) -> list[dict[str, Any]]:
    """Scan for unusual volume."""
    logger.info("Scanning for unusual volume...")

    tasks = [_fetch_ticker_technical(symbol) for symbol in SCAN_UNIVERSE]
    results = await asyncio.gather(*tasks)

    unusual = []
    for data in results:
        if data and data["volume_ratio"] >= min_ratio:
            unusual.append(data)

    # Sort by volume ratio
    unusual.sort(key=lambda x: x["volume_ratio"], reverse=True)
    return unusual[:10]


async def scan_rsi_extremes() -> dict[str, list[dict[str, Any]]]:
    """Scan for RSI extremes (oversold/overbought)."""
    logger.info("Scanning for RSI extremes...")

    tasks = [_fetch_ticker_technical(symbol) for symbol in SCAN_UNIVERSE]
    results = await asyncio.gather(*tasks)

    oversold = []  # RSI < 30
    overbought = []  # RSI > 70

    for data in results:
        if not data:
            continue
        if data["rsi"] < 30:
            oversold.append(data)
        elif data["rsi"] > 70:
            overbought.append(data)

    oversold.sort(key=lambda x: x["rsi"])
    overbought.sort(key=lambda x: x["rsi"], reverse=True)

    return {
        "oversold": oversold[:5],
        "overbought": overbought[:5],
    }


async def scan_top_movers() -> dict[str, list[dict[str, Any]]]:
    """Scan for top gainers and losers."""
    logger.info("Scanning for top movers...")

    tasks = [_fetch_ticker_technical(symbol) for symbol in SCAN_UNIVERSE]
    results = await asyncio.gather(*tasks)

    valid_results = [r for r in results if r]

    gainers = sorted(valid_results, key=lambda x: x["change_pct"], reverse=True)[:5]
    losers = sorted(valid_results, key=lambda x: x["change_pct"])[:5]

    return {
        "gainers": gainers,
        "losers": losers,
    }


def format_screener_results(scan_type: str, results: list[dict[str, Any]] | dict[str, Any]) -> str:
    """Format screener results into readable message."""

    lines = [f"🔍 <b>SCREENER: {scan_type.upper()}</b>\n"]

    if scan_type == "breakouts":
        if not results:
            lines.append("Нет пробоев с высоким объемом.")
        else:
            lines.append("<b>📈 BREAKOUTS (пробой + объем):</b>\n")
            for i, data in enumerate(results[:5], 1):
                lines.append(
                    f"{i}. <b>{data['symbol']}</b> @ ${data['price']:.2f} "
                    f"({data['change_pct']:+.2f}%)\n"
                    f"   Объем: {data['volume_ratio']:.1f}x средний\n"
                    f"   Пробил: ${data['recent_high']:.2f}\n"
                )

    elif scan_type == "unusual_volume":
        if not results:
            lines.append("Нет аномального объема.")
        else:
            lines.append("<b>💥 UNUSUAL VOLUME:</b>\n")
            for i, data in enumerate(results[:5], 1):
                lines.append(
                    f"{i}. <b>{data['symbol']}</b> @ ${data['price']:.2f} "
                    f"({data['change_pct']:+.2f}%)\n"
                    f"   Объем: {data['volume_ratio']:.1f}x средний\n"
                )

    elif scan_type == "rsi_extremes":
        oversold = results.get("oversold", [])
        overbought = results.get("overbought", [])

        if oversold:
            lines.append("<b>📉 OVERSOLD (RSI < 30):</b>\n")
            for data in oversold:
                lines.append(
                    f"• <b>{data['symbol']}</b>: RSI {data['rsi']:.1f} "
                    f"(${data['price']:.2f}, {data['change_pct']:+.2f}%)\n"
                )
            lines.append("")

        if overbought:
            lines.append("<b>📈 OVERBOUGHT (RSI > 70):</b>\n")
            for data in overbought:
                lines.append(
                    f"• <b>{data['symbol']}</b>: RSI {data['rsi']:.1f} "
                    f"(${data['price']:.2f}, {data['change_pct']:+.2f}%)\n"
                )

    elif scan_type == "top_movers":
        gainers = results.get("gainers", [])
        losers = results.get("losers", [])

        if gainers:
            lines.append("<b>🚀 TOP GAINERS:</b>\n")
            for data in gainers:
                lines.append(
                    f"• <b>{data['symbol']}</b>: ${data['price']:.2f} "
                    f"({data['change_pct']:+.2f}%)\n"
                )
            lines.append("")

        if losers:
            lines.append("<b>💥 TOP LOSERS:</b>\n")
            for data in losers:
                lines.append(
                    f"• <b>{data['symbol']}</b>: ${data['price']:.2f} "
                    f"({data['change_pct']:+.2f}%)\n"
                )

    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M UTC")
    lines.append(f"\n<i>Обновлено: {timestamp}</i>")

    return "".join(lines)

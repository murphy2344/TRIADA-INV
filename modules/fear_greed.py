"""Fear & Greed Dashboard - sentiment indicators visualization.

Indicators:
- CNN Fear & Greed Index (crypto)
- VIX (volatility)
- Put/Call Ratio
- Market Breadth (advance/decline)
- High/Low Index
"""
import asyncio
import logging
from datetime import datetime
from typing import Any

import aiohttp
import yfinance as yf

logger = logging.getLogger(__name__)


async def get_fear_greed_crypto() -> dict[str, Any] | None:
    """Get crypto Fear & Greed Index from alternative.me API."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.alternative.me/fng/",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                data = await response.json()
                value = int(data["data"][0]["value"])
                classification = data["data"][0]["value_classification"]

                return {
                    "value": value,
                    "classification": classification,
                    "emoji": _get_fng_emoji(value),
                }
    except Exception as e:
        logger.error(f"Failed to fetch Fear & Greed Index: {e}")
        return None


def _get_fng_emoji(value: int) -> str:
    """Return emoji based on Fear & Greed value."""
    if value <= 25:
        return "😱"  # Extreme Fear
    elif value <= 45:
        return "😰"  # Fear
    elif value <= 55:
        return "😐"  # Neutral
    elif value <= 75:
        return "😃"  # Greed
    else:
        return "🤑"  # Extreme Greed


async def get_vix_level() -> dict[str, Any] | None:
    """Get VIX (volatility index) level."""
    try:
        ticker = await asyncio.to_thread(yf.Ticker, "^VIX")
        hist = await asyncio.to_thread(lambda: ticker.history(period="5d"))

        if hist.empty:
            return None

        current = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2] if len(hist) >= 2 else current
        change = current - prev

        # VIX interpretation
        if current < 12:
            level = "Очень низкая волатильность"
            emoji = "😴"
        elif current < 20:
            level = "Низкая волатильность"
            emoji = "😌"
        elif current < 30:
            level = "Умеренная волатильность"
            emoji = "😐"
        elif current < 40:
            level = "Высокая волатильность"
            emoji = "😰"
        else:
            level = "Экстремальная волатильность"
            emoji = "😱"

        return {
            "value": current,
            "change": change,
            "level": level,
            "emoji": emoji,
        }
    except Exception as e:
        logger.error(f"Failed to fetch VIX: {e}")
        return None


async def get_put_call_ratio() -> dict[str, Any] | None:
    """Get Put/Call ratio (approximation using VIX)."""
    try:
        # Note: Real put/call ratio requires options data from CBOE
        # This is a simplified version using market indicators
        ticker = await asyncio.to_thread(yf.Ticker, "^VIX")
        hist = await asyncio.to_thread(lambda: ticker.history(period="5d"))

        if hist.empty:
            return None

        vix = hist["Close"].iloc[-1]

        # Rough approximation: higher VIX = more puts being bought
        # Normal P/C ratio is around 0.7-1.0
        estimated_pc = 0.5 + (vix / 40)  # Simplified formula

        if estimated_pc < 0.7:
            sentiment = "Bullish (мало защиты)"
            emoji = "🟢"
        elif estimated_pc < 1.0:
            sentiment = "Нейтральный"
            emoji = "😐"
        else:
            sentiment = "Bearish (много защиты)"
            emoji = "🔴"

        return {
            "value": estimated_pc,
            "sentiment": sentiment,
            "emoji": emoji,
            "note": "Приблизительная оценка на основе VIX"
        }
    except Exception as e:
        logger.error(f"Failed to estimate Put/Call ratio: {e}")
        return None


async def get_market_breadth() -> dict[str, Any] | None:
    """Get market breadth (advancing vs declining stocks)."""
    try:
        # Use major indices as proxy for market breadth
        indices = ["^GSPC", "^IXIC", "^DJI"]

        advancing = 0
        declining = 0

        for symbol in indices:
            ticker = await asyncio.to_thread(yf.Ticker, symbol)
            hist = await asyncio.to_thread(lambda: ticker.history(period="2d"))

            if not hist.empty and len(hist) >= 2:
                current = hist["Close"].iloc[-1]
                prev = hist["Close"].iloc[-2]

                if current > prev:
                    advancing += 1
                else:
                    declining += 1

        total = advancing + declining
        if total == 0:
            return None

        advance_pct = (advancing / total) * 100

        if advance_pct >= 80:
            breadth = "Очень сильный рост"
            emoji = "🚀"
        elif advance_pct >= 60:
            breadth = "Рост преобладает"
            emoji = "🟢"
        elif advance_pct >= 40:
            breadth = "Смешанный"
            emoji = "😐"
        elif advance_pct >= 20:
            breadth = "Падение преобладает"
            emoji = "🔴"
        else:
            breadth = "Сильное падение"
            emoji = "💥"

        return {
            "advancing": advancing,
            "declining": declining,
            "advance_pct": advance_pct,
            "breadth": breadth,
            "emoji": emoji,
        }
    except Exception as e:
        logger.error(f"Failed to get market breadth: {e}")
        return None


async def fetch_all_indicators() -> dict[str, Any]:
    """Fetch all sentiment indicators."""
    results = await asyncio.gather(
        get_fear_greed_crypto(),
        get_vix_level(),
        get_put_call_ratio(),
        get_market_breadth(),
        return_exceptions=True
    )

    return {
        "fear_greed": results[0] if not isinstance(results[0], Exception) else None,
        "vix": results[1] if not isinstance(results[1], Exception) else None,
        "put_call": results[2] if not isinstance(results[2], Exception) else None,
        "breadth": results[3] if not isinstance(results[3], Exception) else None,
    }


def format_dashboard(indicators: dict[str, Any]) -> str:
    """Format Fear & Greed dashboard into readable message."""
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M UTC")

    lines = [
        f"📊 <b>FEAR & GREED DASHBOARD</b> — {timestamp}\n"
    ]

    # Fear & Greed Index (Crypto)
    fng = indicators.get("fear_greed")
    if fng:
        lines.append(
            f"<b>📈 Fear & Greed Index (Crypto):</b>\n"
            f"{fng['emoji']} <b>{fng['value']}/100</b> — {fng['classification']}\n"
        )

    # VIX
    vix = indicators.get("vix")
    if vix:
        change_emoji = "📈" if vix['change'] > 0 else "📉"
        lines.append(
            f"<b>💹 VIX (Волатильность):</b>\n"
            f"{vix['emoji']} <b>{vix['value']:.2f}</b> ({vix['change']:+.2f}) {change_emoji}\n"
            f"{vix['level']}\n"
        )

    # Put/Call Ratio
    pc = indicators.get("put_call")
    if pc:
        lines.append(
            f"<b>⚖️ Put/Call Ratio:</b>\n"
            f"{pc['emoji']} <b>{pc['value']:.2f}</b> — {pc['sentiment']}\n"
            f"<i>{pc.get('note', '')}</i>\n"
        )

    # Market Breadth
    breadth = indicators.get("breadth")
    if breadth:
        lines.append(
            f"<b>📊 Market Breadth:</b>\n"
            f"{breadth['emoji']} {breadth['advancing']} растут, {breadth['declining']} падают\n"
            f"{breadth['breadth']} ({breadth['advance_pct']:.0f}% в плюсе)\n"
        )

    # Overall sentiment
    lines.append("\n<b>🎯 Общий вывод:</b>")

    # Simple sentiment aggregation
    bullish_signals = 0
    bearish_signals = 0

    if fng and fng['value'] > 55:
        bullish_signals += 1
    elif fng and fng['value'] < 45:
        bearish_signals += 1

    if vix and vix['value'] < 20:
        bullish_signals += 1
    elif vix and vix['value'] > 30:
        bearish_signals += 1

    if breadth and breadth['advance_pct'] > 60:
        bullish_signals += 1
    elif breadth and breadth['advance_pct'] < 40:
        bearish_signals += 1

    if bullish_signals > bearish_signals:
        lines.append("🟢 Настроение <b>бычье</b> — преобладает оптимизм")
    elif bearish_signals > bullish_signals:
        lines.append("🔴 Настроение <b>медвежье</b> — преобладает страх")
    else:
        lines.append("😐 Настроение <b>нейтральное</b> — рынок в балансе")

    return "\n".join(lines)

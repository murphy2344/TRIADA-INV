"""AI Trade Ideas - personalized trading suggestions.

Analyzes user's portfolio, watchlist, and current market conditions
to generate actionable trade ideas.
"""
import asyncio
import logging
from typing import Any
from datetime import datetime

import yfinance as yf
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


async def _analyze_ticker_opportunity(ticker: str) -> dict[str, Any] | None:
    """Analyze a ticker for trading opportunity."""
    try:
        stock = await asyncio.to_thread(yf.Ticker, ticker)
        info = await asyncio.to_thread(lambda: stock.info)
        hist = await asyncio.to_thread(lambda: stock.history(period="6mo"))

        if hist.empty or len(hist) < 50:
            return None

        current_price = hist["Close"].iloc[-1]

        # Calculate technical indicators
        # 1. RSI (14-day)
        delta = hist["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1] if not rsi.empty else 50

        # 2. Moving averages
        sma_20 = hist["Close"].rolling(window=20).mean().iloc[-1]
        sma_50 = hist["Close"].rolling(window=50).mean().iloc[-1]

        # 3. Price momentum (1M, 3M)
        price_1m_ago = hist["Close"].iloc[-21] if len(hist) >= 21 else current_price
        price_3m_ago = hist["Close"].iloc[-63] if len(hist) >= 63 else current_price

        momentum_1m = ((current_price - price_1m_ago) / price_1m_ago) * 100
        momentum_3m = ((current_price - price_3m_ago) / price_3m_ago) * 100

        # 4. Volatility
        returns = hist["Close"].pct_change().dropna()
        volatility = returns.std() * np.sqrt(252) * 100 if len(returns) > 20 else 0

        # Generate signals
        signals = []
        score = 0

        # RSI signals
        if current_rsi < 30:
            signals.append("RSI < 30 (перепродан)")
            score += 2
        elif current_rsi > 70:
            signals.append("RSI > 70 (перекуплен)")
            score -= 2

        # Moving average signals
        if current_price > sma_20 > sma_50:
            signals.append("Цена выше SMA(20) и SMA(50)")
            score += 1
        elif current_price < sma_20 < sma_50:
            signals.append("Цена ниже SMA(20) и SMA(50)")
            score -= 1

        # Momentum signals
        if momentum_1m > 10 and momentum_3m > 15:
            signals.append("Сильный восходящий тренд")
            score += 2
        elif momentum_1m < -10 and momentum_3m < -15:
            signals.append("Сильный нисходящий тренд")
            score -= 2

        # Valuation signals
        pe_ratio = info.get("trailingPE")
        if pe_ratio and pe_ratio < 15:
            signals.append(f"Низкий P/E: {pe_ratio:.1f}")
            score += 1
        elif pe_ratio and pe_ratio > 40:
            signals.append(f"Высокий P/E: {pe_ratio:.1f}")
            score -= 1

        # Determine action
        if score >= 3:
            action = "BUY"
            action_emoji = "🟢"
            reason = "Сильный сигнал на покупку"
        elif score <= -3:
            action = "SELL"
            action_emoji = "🔴"
            reason = "Сильный сигнал на продажу"
        elif score > 0:
            action = "WATCH"
            action_emoji = "🟡"
            reason = "Слабый сигнал на покупку"
        else:
            action = "NEUTRAL"
            action_emoji = "⚪"
            reason = "Нейтральный сигнал"

        return {
            "ticker": ticker,
            "name": info.get("shortName", ticker),
            "current_price": current_price,
            "action": action,
            "action_emoji": action_emoji,
            "reason": reason,
            "score": score,
            "signals": signals,
            "rsi": current_rsi,
            "volatility": volatility,
            "momentum_1m": momentum_1m,
        }

    except Exception as e:
        logger.error(f"Failed to analyze {ticker}: {e}")
        return None


async def generate_trade_ideas(
    portfolio_tickers: list[str] = None,
    watchlist_tickers: list[str] = None,
) -> dict[str, Any]:
    """Generate personalized trade ideas based on portfolio and watchlist."""

    # Combine tickers from portfolio and watchlist
    all_tickers = set()
    if portfolio_tickers:
        all_tickers.update(portfolio_tickers)
    if watchlist_tickers:
        all_tickers.update(watchlist_tickers)

    # If no tickers, use popular ones
    if not all_tickers:
        all_tickers = {"AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META"}

    all_tickers = list(all_tickers)[:10]  # Limit to 10 tickers

    # Analyze all tickers
    tasks = [_analyze_ticker_opportunity(ticker) for ticker in all_tickers]
    results = await asyncio.gather(*tasks)

    # Filter out None results
    ideas = [r for r in results if r is not None]

    if not ideas:
        return {"error": "Could not generate trade ideas"}

    # Sort by score (best ideas first)
    ideas.sort(key=lambda x: abs(x["score"]), reverse=True)

    # Categorize
    buy_ideas = [i for i in ideas if i["action"] == "BUY"]
    sell_ideas = [i for i in ideas if i["action"] == "SELL"]
    watch_ideas = [i for i in ideas if i["action"] == "WATCH"]

    return {
        "ideas": ideas[:5],  # Top 5 ideas
        "buy": buy_ideas,
        "sell": sell_ideas,
        "watch": watch_ideas,
        "analyzed": len(ideas),
    }


def format_trade_ideas(data: dict[str, Any]) -> str:
    """Format trade ideas into readable message."""

    if "error" in data:
        return f"❌ {data['error']}"

    ideas = data["ideas"]

    lines = [
        "💡 <b>AI TRADE IDEAS</b>\n",
        f"<i>Проанализировано {data['analyzed']} тикеров</i>\n",
    ]

    # Top ideas
    lines.append("<b>🎯 Топ идеи:</b>\n")

    for idea in ideas:
        lines.append(
            f"{idea['action_emoji']} <b>{idea['ticker']}</b> — {idea['action']}"
        )
        lines.append(f"  Цена: ${idea['current_price']:.2f}")
        lines.append(f"  {idea['reason']}")

        if idea["signals"]:
            lines.append(f"  Сигналы:")
            for signal in idea["signals"][:3]:  # Max 3 signals
                lines.append(f"    • {signal}")

        lines.append("")

    # Summary by category
    if data["buy"]:
        lines.append(f"<b>🟢 На покупку ({len(data['buy'])}):</b>")
        tickers = [i["ticker"] for i in data["buy"][:5]]
        lines.append(f"{', '.join(tickers)}\n")

    if data["sell"]:
        lines.append(f"<b>🔴 На продажу ({len(data['sell'])}):</b>")
        tickers = [i["ticker"] for i in data["sell"][:5]]
        lines.append(f"{', '.join(tickers)}\n")

    if data["watch"]:
        lines.append(f"<b>🟡 Наблюдать ({len(data['watch'])}):</b>")
        tickers = [i["ticker"] for i in data["watch"][:5]]
        lines.append(f"{', '.join(tickers)}\n")

    lines.append(
        "<i>⚠️ Это не финансовая рекомендация. "
        "Всегда проводите собственный анализ перед инвестициями.</i>"
    )

    return "\n".join(lines)

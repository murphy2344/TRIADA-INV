"""Backtesting - simulate historical trades.

Features:
- Buy/Sell at historical dates
- Calculate returns and P&L
- Show what you would have made
- Compare with S&P 500 benchmark
"""
import asyncio
import logging
from typing import Any
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)


async def backtest_trade(
    action: str,  # "buy" or "sell"
    ticker: str,
    date_str: str,  # "YYYY-MM-DD"
    amount: float,  # dollars
) -> dict[str, Any]:
    """Backtest a trade from a historical date to today."""

    try:
        # Parse date
        trade_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD"}

    if trade_date >= datetime.now():
        return {"error": "Date must be in the past"}

    if trade_date < datetime.now() - timedelta(days=365 * 20):
        return {"error": "Maximum lookback is 20 years"}

    if amount <= 0:
        return {"error": "Amount must be positive"}

    # Fetch historical data
    try:
        stock = await asyncio.to_thread(yf.Ticker, ticker)
        # Fetch from trade date to today
        hist = await asyncio.to_thread(
            lambda: stock.history(start=trade_date, end=datetime.now())
        )

        if hist.empty:
            return {"error": f"No data available for {ticker} from {date_str}"}

        # Get info for company name
        info = await asyncio.to_thread(lambda: stock.info)
        name = info.get("shortName", ticker)

    except Exception as e:
        logger.error(f"Failed to fetch data for {ticker}: {e}")
        return {"error": f"Could not fetch data for {ticker}"}

    # Find the actual entry price (first available date >= trade_date)
    entry_price = hist["Close"].iloc[0]
    entry_date = hist.index[0]

    # Current price
    current_price = hist["Close"].iloc[-1]
    current_date = hist.index[-1]

    # Calculate returns
    if action == "buy":
        shares = amount / entry_price
        current_value = shares * current_price
        pnl = current_value - amount
        pnl_pct = (pnl / amount) * 100
        annualized_return = (
            ((current_value / amount) ** (365 / (current_date - entry_date).days)) - 1
        ) * 100

    elif action == "sell":
        # Short selling
        shares = amount / entry_price
        # When you short, you sell first, then buy back
        # Profit if price goes down
        buyback_cost = shares * current_price
        pnl = amount - buyback_cost  # Profit if current < entry
        pnl_pct = (pnl / amount) * 100
        annualized_return = (
            ((amount / buyback_cost) ** (365 / (current_date - entry_date).days)) - 1
        ) * 100

    else:
        return {"error": "Action must be 'buy' or 'sell'"}

    # Benchmark: S&P 500
    try:
        spy = await asyncio.to_thread(yf.Ticker, "SPY")
        spy_hist = await asyncio.to_thread(
            lambda: spy.history(start=entry_date, end=current_date)
        )

        if not spy_hist.empty and len(spy_hist) > 1:
            spy_entry = spy_hist["Close"].iloc[0]
            spy_current = spy_hist["Close"].iloc[-1]
            spy_return = ((spy_current - spy_entry) / spy_entry) * 100
            spy_annualized = (
                ((spy_current / spy_entry) ** (365 / (current_date - entry_date).days)) - 1
            ) * 100
        else:
            spy_return = None
            spy_annualized = None

    except Exception:
        spy_return = None
        spy_annualized = None

    return {
        "ticker": ticker,
        "name": name,
        "action": action,
        "entry_date": entry_date.strftime("%Y-%m-%d"),
        "entry_price": entry_price,
        "current_date": current_date.strftime("%Y-%m-%d"),
        "current_price": current_price,
        "amount": amount,
        "shares": shares,
        "current_value": current_value if action == "buy" else buyback_cost,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "annualized_return": annualized_return,
        "days": (current_date - entry_date).days,
        "spy_return": spy_return,
        "spy_annualized": spy_annualized,
    }


def format_backtest(result: dict[str, Any]) -> str:
    """Format backtest result into readable message."""

    if "error" in result:
        return f"❌ {result['error']}"

    lines = ["📈 <b>BACKTEST RESULT</b>\n"]

    # Trade details
    action_emoji = "📈" if result["action"] == "buy" else "📉"
    action_text = "Покупка" if result["action"] == "buy" else "Шорт"

    lines.append(f"{action_emoji} <b>{action_text} {result['ticker']}</b> ({result['name']})")
    lines.append("")

    # Entry
    lines.append(f"<b>Вход ({result['entry_date']}):</b>")
    lines.append(f"• Цена: ${result['entry_price']:.2f}")
    lines.append(f"• Сумма: ${result['amount']:,.2f}")
    lines.append(f"• Акций: {result['shares']:.4f}")
    lines.append("")

    # Current
    lines.append(f"<b>Сейчас ({result['current_date']}):</b>")
    lines.append(f"• Цена: ${result['current_price']:.2f}")
    lines.append(f"• Стоимость: ${result['current_value']:,.2f}")
    lines.append("")

    # Performance
    pnl_emoji = "🟢" if result["pnl"] >= 0 else "🔴"
    lines.append(f"<b>{pnl_emoji} Результат:</b>")
    lines.append(f"• P&L: ${result['pnl']:+,.2f} ({result['pnl_pct']:+.2f}%)")
    lines.append(f"• Период: {result['days']} дней")
    lines.append(f"• Годовая доходность: {result['annualized_return']:+.2f}%")
    lines.append("")

    # Benchmark
    if result["spy_return"] is not None:
        lines.append(f"<b>📊 Сравнение с S&P 500:</b>")
        lines.append(f"• S&P 500 за период: {result['spy_return']:+.2f}%")
        lines.append(f"• S&P 500 годовая: {result['spy_annualized']:+.2f}%")

        outperform = result["pnl_pct"] - result["spy_return"]
        if outperform > 0:
            lines.append(f"• <b>Вы опередили рынок на {outperform:+.2f}%</b> 🎯")
        elif outperform < 0:
            lines.append(f"• <b>Рынок опередил вас на {abs(outperform):.2f}%</b>")
        else:
            lines.append("• <b>Наравне с рынком</b>")

    return "\n".join(lines)

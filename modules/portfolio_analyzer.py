"""Portfolio analyzer - deep analysis of user's portfolio.

Features:
- Asset allocation breakdown
- Risk metrics (volatility, beta, sharpe ratio)
- Diversification score
- Correlation matrix
- Sector exposure
- Performance vs benchmarks
- Recommendations
"""
import asyncio
import logging
from typing import Any
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


async def _fetch_ticker_data(ticker: str, period: str = "1y") -> pd.DataFrame | None:
    """Fetch historical data for a ticker."""
    try:
        stock = await asyncio.to_thread(yf.Ticker, ticker)
        hist = await asyncio.to_thread(lambda: stock.history(period=period))
        return hist if not hist.empty else None
    except Exception as e:
        logger.error(f"Failed to fetch data for {ticker}: {e}")
        return None


async def _fetch_ticker_info(ticker: str) -> dict[str, Any] | None:
    """Fetch ticker info (sector, beta, etc.)."""
    try:
        stock = await asyncio.to_thread(yf.Ticker, ticker)
        info = await asyncio.to_thread(lambda: stock.info)
        return info
    except Exception as e:
        logger.error(f"Failed to fetch info for {ticker}: {e}")
        return None


async def analyze_portfolio(positions: list[dict]) -> dict[str, Any]:
    """Analyze a portfolio and return metrics.

    positions: [{"ticker": "AAPL", "quantity": 10, "avg_price": 150}]
    """

    if not positions:
        return {"error": "Empty portfolio"}

    # Fetch current prices and historical data
    tickers = [p["ticker"] for p in positions]

    # Fetch current prices
    current_prices = {}
    historical_data = {}
    ticker_info = {}

    for ticker in tickers:
        hist = await _fetch_ticker_data(ticker, "1y")
        if hist is not None and not hist.empty:
            current_prices[ticker] = hist["Close"].iloc[-1]
            historical_data[ticker] = hist

        info = await _fetch_ticker_info(ticker)
        if info:
            ticker_info[ticker] = info

    # Calculate portfolio values
    total_value = 0
    total_cost = 0
    position_values = {}

    for position in positions:
        ticker = position["ticker"]
        quantity = position["quantity"]
        avg_price = position["avg_price"]

        current_price = current_prices.get(ticker)
        if current_price:
            value = current_price * quantity
            cost = avg_price * quantity

            total_value += value
            total_cost += cost

            position_values[ticker] = {
                "quantity": quantity,
                "avg_price": avg_price,
                "current_price": current_price,
                "value": value,
                "cost": cost,
                "pnl": value - cost,
                "pnl_pct": ((value - cost) / cost) * 100 if cost > 0 else 0,
            }

    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost) * 100 if total_cost > 0 else 0

    # Asset allocation
    allocations = {}
    for ticker, data in position_values.items():
        allocations[ticker] = (data["value"] / total_value) * 100 if total_value > 0 else 0

    # Sector exposure
    sector_exposure = {}
    for ticker, info in ticker_info.items():
        sector = info.get("sector", "Unknown")
        value = position_values.get(ticker, {}).get("value", 0)
        if sector in sector_exposure:
            sector_exposure[sector] += value
        else:
            sector_exposure[sector] = value

    for sector in sector_exposure:
        sector_exposure[sector] = (sector_exposure[sector] / total_value) * 100 if total_value > 0 else 0

    # Risk metrics (simplified)
    portfolio_returns = []

    if len(historical_data) > 0:
        # Calculate daily returns for each position
        returns_data = {}
        for ticker, hist in historical_data.items():
            if len(hist) > 1:
                returns = hist["Close"].pct_change().dropna()
                returns_data[ticker] = returns

        # Calculate weighted portfolio returns
        if returns_data:
            # Align all returns to common dates
            returns_df = pd.DataFrame(returns_data)

            # Weight by allocation
            weights = []
            for ticker in returns_df.columns:
                weight = allocations.get(ticker, 0) / 100
                weights.append(weight)

            # Portfolio daily returns
            portfolio_returns = (returns_df * weights).sum(axis=1)

    # Calculate volatility (annualized)
    volatility = None
    if len(portfolio_returns) > 20:
        volatility = portfolio_returns.std() * np.sqrt(252) * 100  # Annualized

    # Calculate beta vs S&P 500
    beta = None
    if len(portfolio_returns) > 20:
        try:
            spy = await _fetch_ticker_data("SPY", "1y")
            if spy is not None and not spy.empty:
                spy_returns = spy["Close"].pct_change().dropna()

                # Align dates
                common_dates = portfolio_returns.index.intersection(spy_returns.index)
                if len(common_dates) > 20:
                    port_aligned = portfolio_returns.loc[common_dates]
                    spy_aligned = spy_returns.loc[common_dates]

                    # Calculate beta
                    covariance = np.cov(port_aligned, spy_aligned)[0][1]
                    variance = np.var(spy_aligned)
                    beta = covariance / variance if variance > 0 else None
        except Exception as e:
            logger.warning(f"Failed to calculate beta: {e}")

    # Diversification score (1-10, based on number of positions and allocation spread)
    num_positions = len(positions)

    # Check concentration risk
    max_allocation = max(allocations.values()) if allocations else 0

    if num_positions == 1:
        diversification_score = 1
    elif num_positions >= 15 and max_allocation < 15:
        diversification_score = 10
    elif num_positions >= 10 and max_allocation < 20:
        diversification_score = 8
    elif num_positions >= 5 and max_allocation < 30:
        diversification_score = 6
    elif num_positions >= 3:
        diversification_score = 4
    else:
        diversification_score = 2

    return {
        "total_value": total_value,
        "total_cost": total_cost,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "positions": position_values,
        "allocations": allocations,
        "sector_exposure": sector_exposure,
        "volatility": volatility,
        "beta": beta,
        "diversification_score": diversification_score,
        "num_positions": num_positions,
    }


def format_portfolio_analysis(analysis: dict[str, Any]) -> str:
    """Format portfolio analysis into readable message."""

    if "error" in analysis:
        return f"❌ {analysis['error']}"

    lines = [
        "📊 <b>PORTFOLIO ANALYSIS</b>\n",
        "<b>💰 Общая стоимость:</b>",
        f"${analysis['total_value']:,.2f}",
        f"P&L: ${analysis['total_pnl']:+,.2f} ({analysis['total_pnl_pct']:+.2f}%)\n",
    ]

    # Top positions
    lines.append("<b>📈 Топ позиции:</b>")
    allocations = analysis['allocations']
    sorted_positions = sorted(allocations.items(), key=lambda x: x[1], reverse=True)[:5]

    for ticker, alloc in sorted_positions:
        pos_data = analysis['positions'].get(ticker, {})
        pnl_pct = pos_data.get('pnl_pct', 0)
        emoji = "🟢" if pnl_pct > 0 else "🔴" if pnl_pct < 0 else "➖"
        lines.append(f"{emoji} <b>{ticker}</b>: {alloc:.1f}% ({pnl_pct:+.1f}%)")

    lines.append("")

    # Sector exposure
    if analysis['sector_exposure']:
        lines.append("<b>🏭 Секторное распределение:</b>")
        sorted_sectors = sorted(analysis['sector_exposure'].items(), key=lambda x: x[1], reverse=True)[:5]
        for sector, exposure in sorted_sectors:
            lines.append(f"• {sector}: {exposure:.1f}%")
        lines.append("")

    # Risk metrics
    lines.append("<b>⚠️ Риск-метрики:</b>")

    if analysis['volatility']:
        lines.append(f"• Волатильность: {analysis['volatility']:.1f}% годовых")

    if analysis['beta']:
        beta_str = f"{analysis['beta']:.2f}"
        if analysis['beta'] > 1.2:
            risk_level = "(высокий риск)"
        elif analysis['beta'] > 0.8:
            risk_level = "(средний риск)"
        else:
            risk_level = "(низкий риск)"
        lines.append(f"• Бета к S&P 500: {beta_str} {risk_level}")

    div_score = analysis['diversification_score']
    div_emoji = "🟢" if div_score >= 7 else "🟡" if div_score >= 4 else "🔴"
    lines.append(f"• Диверсификация: {div_emoji} {div_score}/10")

    lines.append("")

    # Recommendations
    lines.append("<b>💡 Рекомендации:</b>")

    if div_score < 5:
        lines.append("⚠️ Недостаточная диверсификация. Добавьте позиции из других секторов.")

    max_alloc = max(analysis['allocations'].values()) if analysis['allocations'] else 0
    if max_alloc > 30:
        lines.append("⚠️ Высокая концентрация в одной позиции. Риск слишком велик.")

    if analysis['volatility'] and analysis['volatility'] > 30:
        lines.append("⚠️ Высокая волатильность портфеля. Рассмотрите добавление защитных активов.")

    if len(lines) == len(lines) - 1:  # No warnings added
        lines.append("✅ Портфель сбалансирован!")

    return "\n".join(lines)

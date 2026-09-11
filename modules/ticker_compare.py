"""Ticker comparison - compare multiple tickers side by side.

Compare:
- Price and market cap
- Valuation (P/E, P/S, P/B)
- Growth metrics (revenue, earnings)
- Performance (1M, 3M, 6M, 1Y)
- Correlation matrix
"""
import asyncio
import logging
from typing import Any

import yfinance as yf
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


async def _fetch_ticker_data(ticker: str) -> dict[str, Any] | None:
    """Fetch comprehensive data for a ticker."""
    try:
        stock = await asyncio.to_thread(yf.Ticker, ticker)
        info = await asyncio.to_thread(lambda: stock.info)
        hist = await asyncio.to_thread(lambda: stock.history(period="1y"))

        if hist.empty:
            return None

        current_price = hist["Close"].iloc[-1]

        # Calculate returns
        returns = {}
        if len(hist) >= 21:  # 1 month
            returns["1M"] = ((current_price - hist["Close"].iloc[-21]) / hist["Close"].iloc[-21]) * 100
        if len(hist) >= 63:  # 3 months
            returns["3M"] = ((current_price - hist["Close"].iloc[-63]) / hist["Close"].iloc[-63]) * 100
        if len(hist) >= 126:  # 6 months
            returns["6M"] = ((current_price - hist["Close"].iloc[-126]) / hist["Close"].iloc[-126]) * 100
        if len(hist) >= 252:  # 1 year
            returns["1Y"] = ((current_price - hist["Close"].iloc[-252]) / hist["Close"].iloc[-252]) * 100

        return {
            "ticker": ticker,
            "name": info.get("shortName", ticker),
            "price": current_price,
            "market_cap": info.get("marketCap", 0),
            "pe_ratio": info.get("trailingPE"),
            "ps_ratio": info.get("priceToSalesTrailing12Months"),
            "pb_ratio": info.get("priceToBook"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "profit_margin": info.get("profitMargins"),
            "beta": info.get("beta"),
            "returns": returns,
            "hist": hist["Close"],  # For correlation
        }
    except Exception as e:
        logger.error(f"Failed to fetch data for {ticker}: {e}")
        return None


async def compare_tickers(tickers: list[str]) -> dict[str, Any]:
    """Compare multiple tickers and return analysis."""

    if len(tickers) < 2:
        return {"error": "Need at least 2 tickers to compare"}

    if len(tickers) > 5:
        return {"error": "Maximum 5 tickers allowed"}

    # Fetch data for all tickers
    tasks = [_fetch_ticker_data(ticker.upper()) for ticker in tickers]
    results = await asyncio.gather(*tasks)

    # Filter out None results
    valid_data = [r for r in results if r is not None]

    if len(valid_data) < 2:
        return {"error": "Could not fetch data for enough tickers"}

    # Calculate correlation matrix
    correlations = {}
    if len(valid_data) >= 2:
        # Get price series for all tickers
        price_series = {}
        for data in valid_data:
            price_series[data["ticker"]] = data["hist"]

        # Create DataFrame and calculate correlation
        try:
            df = pd.DataFrame(price_series)
            df = df.dropna()
            if len(df) > 20:
                corr_matrix = df.corr()
                correlations = corr_matrix.to_dict()
        except Exception as e:
            logger.warning(f"Failed to calculate correlations: {e}")

    return {
        "tickers": valid_data,
        "correlations": correlations,
    }


def format_comparison(comparison: dict[str, Any]) -> str:
    """Format comparison into readable message."""

    if "error" in comparison:
        return f"❌ {comparison['error']}"

    tickers = comparison["tickers"]

    lines = ["📊 <b>TICKER COMPARISON</b>\n"]

    # Price and Market Cap
    lines.append("<b>💰 Цена и капитализация:</b>")
    for data in tickers:
        mc = data["market_cap"]
        if mc >= 1e12:
            mc_str = f"${mc/1e12:.2f}T"
        elif mc >= 1e9:
            mc_str = f"${mc/1e9:.2f}B"
        elif mc >= 1e6:
            mc_str = f"${mc/1e6:.2f}M"
        else:
            mc_str = "н/д"

        lines.append(f"• <b>{data['ticker']}</b>: ${data['price']:.2f} | Cap: {mc_str}")

    lines.append("")

    # Valuation
    lines.append("<b>📈 Оценка (чем ниже, тем дешевле):</b>")
    lines.append("<i>P/E | P/S | P/B</i>")
    for data in tickers:
        pe = f"{data['pe_ratio']:.1f}" if data['pe_ratio'] else "н/д"
        ps = f"{data['ps_ratio']:.1f}" if data['ps_ratio'] else "н/д"
        pb = f"{data['pb_ratio']:.1f}" if data['pb_ratio'] else "н/д"
        lines.append(f"• <b>{data['ticker']}</b>: {pe} | {ps} | {pb}")

    lines.append("")

    # Growth
    lines.append("<b>📊 Рост (год к году):</b>")
    for data in tickers:
        rev = f"{data['revenue_growth']*100:+.1f}%" if data['revenue_growth'] else "н/д"
        earn = f"{data['earnings_growth']*100:+.1f}%" if data['earnings_growth'] else "н/д"
        margin = f"{data['profit_margin']*100:.1f}%" if data['profit_margin'] else "н/д"
        lines.append(f"• <b>{data['ticker']}</b>: Выручка {rev} | Прибыль {earn} | Маржа {margin}")

    lines.append("")

    # Performance
    lines.append("<b>🚀 Доходность:</b>")
    periods = ["1M", "3M", "6M", "1Y"]

    for data in tickers:
        returns_str = []
        for period in periods:
            ret = data["returns"].get(period)
            if ret is not None:
                emoji = "🟢" if ret > 0 else "🔴" if ret < 0 else "➖"
                returns_str.append(f"{period}: {emoji}{ret:+.1f}%")
            else:
                returns_str.append(f"{period}: н/д")

        lines.append(f"• <b>{data['ticker']}</b>: {' | '.join(returns_str)}")

    lines.append("")

    # Risk
    lines.append("<b>⚠️ Риск (Beta):</b>")
    for data in tickers:
        beta = data["beta"]
        if beta:
            if beta > 1.2:
                risk = "(высокий)"
            elif beta > 0.8:
                risk = "(средний)"
            else:
                risk = "(низкий)"
            lines.append(f"• <b>{data['ticker']}</b>: {beta:.2f} {risk}")
        else:
            lines.append(f"• <b>{data['ticker']}</b>: н/д")

    # Correlations
    correlations = comparison.get("correlations", {})
    if correlations and len(tickers) >= 2:
        lines.append("\n<b>🔗 Корреляция (насколько движутся вместе):</b>")

        # Show pairwise correlations
        for i, data1 in enumerate(tickers):
            for data2 in tickers[i+1:]:
                t1 = data1["ticker"]
                t2 = data2["ticker"]

                if t1 in correlations and t2 in correlations[t1]:
                    corr = correlations[t1][t2]

                    if corr > 0.7:
                        desc = "сильная"
                        emoji = "🟢"
                    elif corr > 0.3:
                        desc = "умеренная"
                        emoji = "🟡"
                    elif corr > -0.3:
                        desc = "слабая"
                        emoji = "⚪"
                    else:
                        desc = "обратная"
                        emoji = "🔴"

                    lines.append(f"{emoji} {t1} ↔ {t2}: {corr:.2f} ({desc})")

    lines.append("\n<i>P/E = Price/Earnings, P/S = Price/Sales, P/B = Price/Book</i>")

    return "\n".join(lines)

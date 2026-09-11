"""Fundamental analysis: financial statements, peer comparison, analyst ratings."""
import asyncio
import logging
from typing import Any
import yfinance as yf

logger = logging.getLogger(__name__)


async def fetch_fundamentals(ticker: str) -> dict[str, Any] | None:
    """Fetch comprehensive fundamental data for a ticker."""
    try:
        stock = await asyncio.to_thread(yf.Ticker, ticker)
        info = await asyncio.to_thread(lambda: stock.info)

        if not info or "symbol" not in info:
            return None

        # Financial metrics
        data = {
            "symbol": info.get("symbol", ticker.upper()),
            "name": info.get("longName", ticker.upper()),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "market_cap": info.get("marketCap"),
            "enterprise_value": info.get("enterpriseValue"),

            # Price metrics
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "target_price": info.get("targetMeanPrice"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),

            # Valuation ratios
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "peg_ratio": info.get("pegRatio"),
            "ps_ratio": info.get("priceToSalesTrailing12Months"),
            "pb_ratio": info.get("priceToBook"),
            "ev_to_ebitda": info.get("enterpriseToEbitda"),

            # Profitability
            "profit_margin": info.get("profitMargins"),
            "operating_margin": info.get("operatingMargins"),
            "roe": info.get("returnOnEquity"),
            "roa": info.get("returnOnAssets"),

            # Growth
            "revenue": info.get("totalRevenue"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "earnings_quarterly_growth": info.get("earningsQuarterlyGrowth"),

            # Dividends
            "dividend_yield": info.get("dividendYield"),
            "payout_ratio": info.get("payoutRatio"),
            "ex_dividend_date": info.get("exDividendDate"),

            # Financial health
            "total_cash": info.get("totalCash"),
            "total_debt": info.get("totalDebt"),
            "debt_to_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "quick_ratio": info.get("quickRatio"),

            # Cash flow
            "operating_cash_flow": info.get("operatingCashflow"),
            "free_cash_flow": info.get("freeCashflow"),
        }

        return data

    except Exception as e:
        logger.error(f"Error fetching fundamentals for {ticker}: {e}")
        return None


def format_fundamentals(data: dict[str, Any]) -> str:
    """Format fundamental data as a readable message."""

    def fmt_num(val, suffix="", decimals=2):
        """Format number with K/M/B suffix."""
        if val is None:
            return "н/д"
        if abs(val) >= 1e9:
            return f"${val/1e9:.{decimals}f}B{suffix}"
        if abs(val) >= 1e6:
            return f"${val/1e6:.{decimals}f}M{suffix}"
        if abs(val) >= 1e3:
            return f"${val/1e3:.{decimals}f}K{suffix}"
        return f"${val:.{decimals}f}{suffix}"

    def fmt_pct(val):
        """Format percentage."""
        if val is None:
            return "н/д"
        return f"{val*100:+.2f}%"

    def fmt_ratio(val):
        """Format ratio."""
        if val is None:
            return "н/д"
        return f"{val:.2f}"

    # Header
    text = f"📊 <b>{data['name']}</b> ({data['symbol']})\n"
    text += f"🏢 {data['sector']} • {data['industry']}\n\n"

    # Price & Target
    price = data['current_price']
    target = data['target_price']
    if price and target:
        upside = ((target - price) / price) * 100
        text += f"💰 <b>Цена:</b> ${price:.2f}\n"
        text += f"🎯 <b>Target:</b> ${target:.2f} ({upside:+.1f}% upside)\n"
    elif price:
        text += f"💰 <b>Цена:</b> ${price:.2f}\n"

    if data['52w_low'] and data['52w_high']:
        text += f"📈 <b>52w Range:</b> ${data['52w_low']:.2f} - ${data['52w_high']:.2f}\n"

    text += "\n"

    # Size
    text += "<b>📏 Размер компании:</b>\n"
    text += f"  Market Cap: {fmt_num(data['market_cap'])}\n"
    text += f"  Enterprise Value: {fmt_num(data['enterprise_value'])}\n"
    text += f"  Revenue (TTM): {fmt_num(data['revenue'])}\n\n"

    # Valuation
    text += "<b>💎 Оценка (Valuation):</b>\n"
    text += f"  P/E: {fmt_ratio(data['pe_ratio'])}"
    if data['forward_pe']:
        text += f" (forward: {fmt_ratio(data['forward_pe'])})"
    text += "\n"
    text += f"  PEG: {fmt_ratio(data['peg_ratio'])}\n"
    text += f"  P/S: {fmt_ratio(data['ps_ratio'])}\n"
    text += f"  P/B: {fmt_ratio(data['pb_ratio'])}\n"
    text += f"  EV/EBITDA: {fmt_ratio(data['ev_to_ebitda'])}\n\n"

    # Profitability
    text += "<b>💰 Рентабельность:</b>\n"
    text += f"  Profit Margin: {fmt_pct(data['profit_margin'])}\n"
    text += f"  Operating Margin: {fmt_pct(data['operating_margin'])}\n"
    text += f"  ROE: {fmt_pct(data['roe'])}\n"
    text += f"  ROA: {fmt_pct(data['roa'])}\n\n"

    # Growth
    text += "<b>📈 Рост:</b>\n"
    text += f"  Revenue Growth: {fmt_pct(data['revenue_growth'])}\n"
    text += f"  Earnings Growth: {fmt_pct(data['earnings_growth'])}\n"
    text += f"  Earnings Growth (QoQ): {fmt_pct(data['earnings_quarterly_growth'])}\n\n"

    # Dividends
    if data['dividend_yield']:
        text += "<b>💵 Дивиденды:</b>\n"
        text += f"  Yield: {fmt_pct(data['dividend_yield'])}\n"
        text += f"  Payout Ratio: {fmt_pct(data['payout_ratio'])}\n\n"

    # Financial Health
    text += "<b>💪 Финансовое здоровье:</b>\n"
    text += f"  Cash: {fmt_num(data['total_cash'])}\n"
    text += f"  Debt: {fmt_num(data['total_debt'])}\n"
    text += f"  Debt/Equity: {fmt_ratio(data['debt_to_equity'])}\n"
    text += f"  Current Ratio: {fmt_ratio(data['current_ratio'])}\n"
    text += f"  Quick Ratio: {fmt_ratio(data['quick_ratio'])}\n\n"

    # Cash Flow
    text += "<b>💸 Денежные потоки:</b>\n"
    text += f"  Operating CF: {fmt_num(data['operating_cash_flow'])}\n"
    text += f"  Free CF: {fmt_num(data['free_cash_flow'])}\n\n"

    text += "<i>Источник: Yahoo Finance</i>"

    return text


async def fetch_peers(ticker: str) -> dict[str, Any] | None:
    """Fetch peer comparison data."""
    try:
        stock = await asyncio.to_thread(yf.Ticker, ticker)
        info = await asyncio.to_thread(lambda: stock.info)

        if not info or "symbol" not in info:
            return None

        # Get company sector to find peers
        sector = info.get("sector")
        industry = info.get("industry")

        # For now, we'll get data for the main ticker
        # In a full implementation, you'd query similar companies
        # Using sector ETFs or industry peers from a database

        main_data = {
            "symbol": ticker.upper(),
            "name": info.get("longName", ticker.upper()),
            "sector": sector,
            "industry": industry,
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "ps_ratio": info.get("priceToSalesTrailing12Months"),
            "pb_ratio": info.get("priceToBook"),
            "revenue_growth": info.get("revenueGrowth"),
            "profit_margin": info.get("profitMargins"),
            "roe": info.get("returnOnEquity"),
            "beta": info.get("beta"),
        }

        # Common peers by sector (simplified)
        peer_map = {
            "Technology": ["AAPL", "MSFT", "GOOGL", "META", "NVDA"],
            "Financial Services": ["JPM", "BAC", "WFC", "C", "GS"],
            "Healthcare": ["JNJ", "UNH", "PFE", "ABBV", "TMO"],
            "Consumer Cyclical": ["AMZN", "TSLA", "HD", "NKE", "MCD"],
            "Communication Services": ["META", "GOOGL", "NFLX", "DIS", "T"],
            "Consumer Defensive": ["PG", "KO", "PEP", "WMT", "COST"],
            "Energy": ["XOM", "CVX", "COP", "SLB", "EOG"],
            "Industrials": ["BA", "CAT", "HON", "UNP", "GE"],
        }

        peer_tickers = peer_map.get(sector, [])
        # Remove main ticker from peers if present
        peer_tickers = [p for p in peer_tickers if p != ticker.upper()][:4]

        # Fetch peer data
        peers = []
        for peer_ticker in peer_tickers:
            try:
                peer_stock = await asyncio.to_thread(yf.Ticker, peer_ticker)
                peer_info = await asyncio.to_thread(lambda: peer_stock.info)

                peers.append({
                    "symbol": peer_ticker,
                    "name": peer_info.get("longName", peer_ticker),
                    "market_cap": peer_info.get("marketCap"),
                    "pe_ratio": peer_info.get("trailingPE"),
                    "ps_ratio": peer_info.get("priceToSalesTrailing12Months"),
                    "pb_ratio": peer_info.get("priceToBook"),
                    "revenue_growth": peer_info.get("revenueGrowth"),
                    "profit_margin": peer_info.get("profitMargins"),
                    "roe": peer_info.get("returnOnEquity"),
                    "beta": peer_info.get("beta"),
                })
            except Exception:
                continue

        return {
            "main": main_data,
            "peers": peers,
        }

    except Exception as e:
        logger.error(f"Error fetching peers for {ticker}: {e}")
        return None


def format_peers(data: dict[str, Any]) -> str:
    """Format peer comparison as a readable message."""

    def fmt_num(val):
        if val is None:
            return "н/д"
        if abs(val) >= 1e9:
            return f"${val/1e9:.1f}B"
        if abs(val) >= 1e6:
            return f"${val/1e6:.1f}M"
        return f"${val:.0f}"

    def fmt_pct(val):
        if val is None:
            return "н/д"
        return f"{val*100:.1f}%"

    def fmt_ratio(val):
        if val is None:
            return "н/д"
        return f"{val:.2f}"

    main = data["main"]
    peers = data["peers"]

    text = f"🔍 <b>Сравнение с конкурентами</b>\n\n"
    text += f"<b>{main['name']}</b> ({main['symbol']})\n"
    text += f"🏢 {main['sector']} • {main['industry']}\n\n"

    # Comparison table header
    text += "<b>📊 Ключевые метрики:</b>\n\n"

    # Main company
    text += f"<code>{main['symbol']:>6}</code> (ваш выбор)\n"
    text += f"  Cap: {fmt_num(main['market_cap']):>10}\n"
    text += f"  P/E: {fmt_ratio(main['pe_ratio']):>10}  "
    text += f"P/S: {fmt_ratio(main['ps_ratio']):>6}\n"
    text += f"  Margin: {fmt_pct(main['profit_margin']):>7}  "
    text += f"Growth: {fmt_pct(main['revenue_growth']):>6}\n"
    text += f"  ROE: {fmt_pct(main['roe']):>10}  "
    text += f"Beta: {fmt_ratio(main['beta']):>6}\n\n"

    # Peers
    if peers:
        text += "<b>Конкуренты:</b>\n\n"
        for peer in peers:
            text += f"<code>{peer['symbol']:>6}</code> {peer['name'][:20]}\n"
            text += f"  Cap: {fmt_num(peer['market_cap']):>10}\n"
            text += f"  P/E: {fmt_ratio(peer['pe_ratio']):>10}  "
            text += f"P/S: {fmt_ratio(peer['ps_ratio']):>6}\n"
            text += f"  Margin: {fmt_pct(peer['profit_margin']):>7}  "
            text += f"Growth: {fmt_pct(peer['revenue_growth']):>6}\n"
            text += f"  ROE: {fmt_pct(peer['roe']):>10}  "
            text += f"Beta: {fmt_ratio(peer['beta']):>6}\n\n"
    else:
        text += "<i>Не удалось загрузить данные конкурентов</i>\n\n"

    text += "<i>💡 Сравнивайте P/E, margins, ROE с конкурентами для оценки</i>"

    return text


async def fetch_analysts(ticker: str) -> dict[str, Any] | None:
    """Fetch analyst ratings and recommendations."""
    try:
        stock = await asyncio.to_thread(yf.Ticker, ticker)
        info = await asyncio.to_thread(lambda: stock.info)

        if not info or "symbol" not in info:
            return None

        # Analyst recommendations
        data = {
            "symbol": ticker.upper(),
            "name": info.get("longName", ticker.upper()),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "target_mean": info.get("targetMeanPrice"),
            "target_high": info.get("targetHighPrice"),
            "target_low": info.get("targetLowPrice"),
            "recommendation": info.get("recommendationKey", "").upper(),
            "number_of_analysts": info.get("numberOfAnalystOpinions"),

            # Recommendation breakdown
            "strong_buy": info.get("recommendationMean"),  # yfinance uses a 1-5 scale
        }

        # Try to get recommendation trends (upgrades/downgrades)
        try:
            recommendations = await asyncio.to_thread(lambda: stock.recommendations)
            if recommendations is not None and not recommendations.empty:
                recent = recommendations.tail(5).to_dict('records')
                data["recent_changes"] = recent
            else:
                data["recent_changes"] = []
        except Exception:
            data["recent_changes"] = []

        return data

    except Exception as e:
        logger.error(f"Error fetching analyst data for {ticker}: {e}")
        return None


def format_analysts(data: dict[str, Any]) -> str:
    """Format analyst ratings as a readable message."""

    text = f"🎯 <b>Мнение аналитиков</b>\n\n"
    text += f"<b>{data['name']}</b> ({data['symbol']})\n\n"

    # Current price and targets
    price = data['current_price']
    target_mean = data['target_mean']
    target_high = data['target_high']
    target_low = data['target_low']

    if price and target_mean:
        upside = ((target_mean - price) / price) * 100
        text += f"💰 <b>Текущая цена:</b> ${price:.2f}\n\n"
        text += f"<b>🎯 Price Targets:</b>\n"
        text += f"  Средний: ${target_mean:.2f} ({upside:+.1f}%)\n"
        if target_high:
            upside_high = ((target_high - price) / price) * 100
            text += f"  Максимум: ${target_high:.2f} ({upside_high:+.1f}%)\n"
        if target_low:
            upside_low = ((target_low - price) / price) * 100
            text += f"  Минимум: ${target_low:.2f} ({upside_low:+.1f}%)\n"
        text += "\n"

    # Recommendation
    recommendation = data['recommendation']
    num_analysts = data['number_of_analysts']

    if recommendation:
        # Map recommendation to emoji and Russian
        rec_map = {
            "STRONG_BUY": ("🟢🟢", "Сильная покупка"),
            "BUY": ("🟢", "Покупка"),
            "HOLD": ("🟡", "Держать"),
            "SELL": ("🔴", "Продавать"),
            "STRONG_SELL": ("🔴🔴", "Сильная продажа"),
        }
        emoji, rec_text = rec_map.get(recommendation, ("⚪", recommendation))

        text += f"<b>📊 Консенсус:</b> {emoji} {rec_text}\n"
        if num_analysts:
            text += f"<i>На основе {num_analysts} аналитиков</i>\n\n"
        else:
            text += "\n"

    # Recent changes
    recent = data.get("recent_changes", [])
    if recent:
        text += "<b>📰 Недавние изменения:</b>\n"
        for change in recent[-5:]:
            firm = change.get("Firm", "Unknown")
            to_grade = change.get("To Grade", "N/A")
            from_grade = change.get("From Grade", "")

            if from_grade:
                text += f"  • {firm}: {from_grade} → {to_grade}\n"
            else:
                text += f"  • {firm}: {to_grade}\n"
        text += "\n"

    # Interpretation
    if target_mean and price and target_mean > price:
        text += "💡 <i>Аналитики видят потенциал роста</i>\n"
    elif target_mean and price and target_mean < price:
        text += "⚠️ <i>Аналитики считают акцию переоцененной</i>\n"

    text += "\n<i>Источник: Yahoo Finance, Wall Street analysts</i>"

    return text

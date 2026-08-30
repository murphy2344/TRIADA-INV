"""Market snapshot - real-time overview of global markets.

Provides:
- Major indices (S&P 500, Nasdaq, Dow, Russell 2000)
- International indices (FTSE, DAX, Nikkei, Shanghai)
- Currencies (DXY, EUR/USD, GBP/USD)
- Commodities (Gold, Oil, Natural Gas)
- Crypto (BTC, ETH)
- Volatility (VIX)
- Yields (10Y, 2Y)
- Market sentiment indicators
"""
import asyncio
import logging
from datetime import datetime
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)


def _get_emoji(change_pct: float) -> str:
    """Return emoji based on price change."""
    if change_pct >= 2:
        return "🚀"
    elif change_pct >= 0.5:
        return "🟢"
    elif change_pct >= 0:
        return "⬆️"
    elif change_pct >= -0.5:
        return "⬇️"
    elif change_pct >= -2:
        return "🔴"
    else:
        return "💥"


def _format_price(price: float, decimals: int = 2) -> str:
    """Format price with appropriate decimals."""
    return f"{price:,.{decimals}f}"


async def _fetch_ticker_data(symbol: str) -> dict[str, Any] | None:
    """Fetch current price and change for a ticker."""
    try:
        ticker = await asyncio.to_thread(yf.Ticker, symbol)
        info = await asyncio.to_thread(lambda: ticker.info)

        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")

        if not current_price or not prev_close:
            # Fallback to history
            hist = await asyncio.to_thread(
                lambda: ticker.history(period="2d", interval="1d")
            )
            if len(hist) >= 2:
                current_price = hist["Close"].iloc[-1]
                prev_close = hist["Close"].iloc[-2]
            elif len(hist) == 1:
                current_price = hist["Close"].iloc[-1]
                prev_close = current_price
            else:
                return None

        change = current_price - prev_close
        change_pct = (change / prev_close) * 100

        return {
            "symbol": symbol,
            "price": current_price,
            "change": change,
            "change_pct": change_pct,
            "prev_close": prev_close,
        }
    except Exception as e:
        logger.warning(f"Failed to fetch {symbol}: {e}")
        return None


async def fetch_market_snapshot() -> dict[str, Any]:
    """Fetch complete market snapshot."""

    # Define all tickers we want to track
    tickers = {
        "indices": {
            "^GSPC": "S&P 500",
            "^IXIC": "Nasdaq",
            "^DJI": "Dow Jones",
            "^RUT": "Russell 2000",
        },
        "international": {
            "^FTSE": "FTSE 100",
            "^GDAXI": "DAX",
            "^N225": "Nikkei",
            "000001.SS": "Shanghai",
        },
        "currencies": {
            "DX-Y.NYB": "DXY",
            "EURUSD=X": "EUR/USD",
            "GBPUSD=X": "GBP/USD",
        },
        "commodities": {
            "GC=F": "Gold",
            "CL=F": "WTI Oil",
            "NG=F": "Nat Gas",
        },
        "crypto": {
            "BTC-USD": "Bitcoin",
            "ETH-USD": "Ethereum",
        },
        "volatility": {
            "^VIX": "VIX",
        },
        "yields": {
            "^TNX": "10Y Yield",
            "^IRX": "13W Yield",
        },
    }

    results = {}

    for category, symbols in tickers.items():
        results[category] = {}
        tasks = [_fetch_ticker_data(symbol) for symbol in symbols.keys()]
        data_list = await asyncio.gather(*tasks)

        for symbol, name in symbols.items():
            idx = list(symbols.keys()).index(symbol)
            if data_list[idx]:
                results[category][name] = data_list[idx]

    return results


def format_market_snapshot(data: dict[str, Any]) -> str:
    """Format market snapshot into readable message."""

    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M UTC")

    lines = [
        f"📊 <b>MARKET PULSE</b> — {timestamp}\n"
    ]

    # US Indices
    lines.append("<b>🇺🇸 US INDICES:</b>")
    if "indices" in data and data["indices"]:
        for name, ticker_data in data["indices"].items():
            if ticker_data:
                emoji = _get_emoji(ticker_data["change_pct"])
                lines.append(
                    f"• {name}: {_format_price(ticker_data['price'])} "
                    f"({ticker_data['change_pct']:+.2f}%) {emoji}"
                )
    lines.append("")

    # International
    lines.append("<b>🌍 INTERNATIONAL:</b>")
    if "international" in data and data["international"]:
        for name, ticker_data in data["international"].items():
            if ticker_data:
                emoji = _get_emoji(ticker_data["change_pct"])
                lines.append(
                    f"• {name}: {_format_price(ticker_data['price'])} "
                    f"({ticker_data['change_pct']:+.2f}%) {emoji}"
                )
    lines.append("")

    # Crypto
    lines.append("<b>₿ CRYPTO:</b>")
    if "crypto" in data and data["crypto"]:
        for name, ticker_data in data["crypto"].items():
            if ticker_data:
                emoji = _get_emoji(ticker_data["change_pct"])
                lines.append(
                    f"• {name}: ${_format_price(ticker_data['price'])} "
                    f"({ticker_data['change_pct']:+.2f}%) {emoji}"
                )
    lines.append("")

    # Commodities
    lines.append("<b>🥇 COMMODITIES:</b>")
    if "commodities" in data and data["commodities"]:
        for name, ticker_data in data["commodities"].items():
            if ticker_data:
                emoji = _get_emoji(ticker_data["change_pct"])
                lines.append(
                    f"• {name}: ${_format_price(ticker_data['price'])} "
                    f"({ticker_data['change_pct']:+.2f}%) {emoji}"
                )
    lines.append("")

    # Currencies
    lines.append("<b>💱 CURRENCIES:</b>")
    if "currencies" in data and data["currencies"]:
        for name, ticker_data in data["currencies"].items():
            if ticker_data:
                emoji = _get_emoji(ticker_data["change_pct"])
                lines.append(
                    f"• {name}: {_format_price(ticker_data['price'], 4)} "
                    f"({ticker_data['change_pct']:+.2f}%) {emoji}"
                )
    lines.append("")

    # Volatility & Yields
    lines.append("<b>📈 VOLATILITY & YIELDS:</b>")
    if "volatility" in data and data["volatility"]:
        for name, ticker_data in data["volatility"].items():
            if ticker_data:
                vix_emoji = "😱" if ticker_data["price"] > 25 else "😌" if ticker_data["price"] < 15 else "😐"
                lines.append(
                    f"• {name}: {_format_price(ticker_data['price'])} "
                    f"({ticker_data['change_pct']:+.2f}%) {vix_emoji}"
                )

    if "yields" in data and data["yields"]:
        for name, ticker_data in data["yields"].items():
            if ticker_data:
                lines.append(
                    f"• {name}: {_format_price(ticker_data['price'])}%"
                )

    lines.append("\n<i>Обновляется каждые 4 часа</i>")

    return "\n".join(lines)


async def get_market_sentiment() -> str:
    """Determine overall market sentiment."""
    try:
        # Fetch S&P 500 and VIX for quick sentiment
        sp500_data = await _fetch_ticker_data("^GSPC")
        vix_data = await _fetch_ticker_data("^VIX")

        if not sp500_data or not vix_data:
            return "NEUTRAL 😐"

        sp500_change = sp500_data["change_pct"]
        vix_level = vix_data["price"]

        # Determine sentiment
        if sp500_change > 1 and vix_level < 15:
            return "RISK-ON 🚀 (Strong Bullish)"
        elif sp500_change > 0.3 and vix_level < 20:
            return "RISK-ON 🟢 (Bullish)"
        elif sp500_change < -1 and vix_level > 25:
            return "RISK-OFF 💥 (Strong Bearish)"
        elif sp500_change < -0.3 and vix_level > 20:
            return "RISK-OFF 🔴 (Bearish)"
        else:
            return "NEUTRAL 😐 (Mixed)"

    except Exception as e:
        logger.error(f"Failed to determine sentiment: {e}")
        return "UNKNOWN"

"""News fetcher for user's watchlist tickers.

Fetches latest news for tickers in user's watchlist and filters by relevance.
"""
import asyncio
import logging
from typing import Any
from datetime import datetime, timedelta

import yfinance as yf

logger = logging.getLogger(__name__)


async def fetch_ticker_news(ticker: str, limit: int = 5) -> list[dict[str, Any]]:
    """Fetch recent news for a ticker."""
    try:
        stock = await asyncio.to_thread(yf.Ticker, ticker)
        news = await asyncio.to_thread(lambda: stock.news)

        if not news:
            return []

        # Process and filter news
        processed = []
        for item in news[:limit]:
            try:
                # Extract relevant fields
                title = item.get("title", "")
                link = item.get("link", "")
                publisher = item.get("publisher", "Unknown")

                # Parse timestamp
                timestamp = item.get("providerPublishTime")
                if timestamp:
                    pub_date = datetime.fromtimestamp(timestamp)
                    # Only include news from last 7 days
                    if datetime.now() - pub_date > timedelta(days=7):
                        continue
                    date_str = pub_date.strftime("%d.%m %H:%M")
                else:
                    date_str = "н/д"

                processed.append({
                    "ticker": ticker,
                    "title": title,
                    "link": link,
                    "publisher": publisher,
                    "date": date_str,
                })
            except Exception as e:
                logger.warning(f"Failed to process news item for {ticker}: {e}")
                continue

        return processed

    except Exception as e:
        logger.error(f"Failed to fetch news for {ticker}: {e}")
        return []


async def fetch_watchlist_news(tickers: list[str], limit_per_ticker: int = 3) -> dict[str, Any]:
    """Fetch news for all tickers in watchlist."""

    if not tickers:
        return {"error": "Watchlist is empty"}

    # Fetch news for all tickers concurrently
    tasks = [fetch_ticker_news(ticker, limit_per_ticker) for ticker in tickers]
    results = await asyncio.gather(*tasks)

    # Combine all news
    all_news = []
    for news_list in results:
        all_news.extend(news_list)

    if not all_news:
        return {"error": "No recent news found for your watchlist"}

    # Sort by most recent first (approximation based on position)
    # Note: yfinance already returns most recent first

    return {
        "news": all_news,
        "count": len(all_news),
        "tickers": tickers,
    }


def format_news(data: dict[str, Any]) -> str:
    """Format news into readable message."""

    if "error" in data:
        return f"❌ {data['error']}"

    news_items = data["news"]
    tickers = data["tickers"]

    lines = [
        "📰 <b>НОВОСТИ ПО ВАШЕМУ WATCHLIST</b>\n",
        f"<i>Отслеживаю: {', '.join(tickers)}</i>\n",
    ]

    # Group by ticker
    by_ticker = {}
    for item in news_items:
        ticker = item["ticker"]
        if ticker not in by_ticker:
            by_ticker[ticker] = []
        by_ticker[ticker].append(item)

    # Format grouped news
    for ticker, news_list in by_ticker.items():
        lines.append(f"<b>📊 {ticker}</b>")

        for news in news_list[:3]:  # Max 3 per ticker in display
            # Truncate title if too long
            title = news["title"]
            if len(title) > 80:
                title = title[:77] + "..."

            lines.append(f"• <i>{news['date']}</i> — {title}")
            lines.append(f"  <a href='{news['link']}'>Читать</a> | {news['publisher']}")

        lines.append("")

    lines.append(f"<i>Показано {len(news_items)} новостей за последние 7 дней</i>")

    return "\n".join(lines)

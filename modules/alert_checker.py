"""Background alert checker - runs every 5 minutes to check price alerts."""
import asyncio
import logging
import yfinance as yf
from modules import storage

logger = logging.getLogger(__name__)


async def check_alerts(bot, admin_id: str = None):
    """Check all active alerts and notify users when triggered."""
    try:
        alerts = await storage.get_all_active_alerts()
        if not alerts:
            return

        # Group alerts by ticker to minimize API calls
        ticker_alerts = {}
        for alert in alerts:
            ticker = alert['ticker']
            if ticker not in ticker_alerts:
                ticker_alerts[ticker] = []
            ticker_alerts[ticker].append(alert)

        # Fetch prices for all tickers
        tickers_list = list(ticker_alerts.keys())
        prices = await asyncio.to_thread(_fetch_prices, tickers_list)

        triggered_count = 0

        for ticker, ticker_price in prices.items():
            if ticker_price is None:
                continue

            for alert in ticker_alerts[ticker]:
                target = alert['target_price']
                direction = alert['direction']

                triggered = False
                if direction == 'above' and ticker_price >= target:
                    triggered = True
                    emoji = "▲"
                    text = f"пробила уровень вверх"
                elif direction == 'below' and ticker_price <= target:
                    triggered = True
                    emoji = "▼"
                    text = f"пробила уровень вниз"

                if triggered:
                    await storage.mark_alert_triggered(alert['id'])
                    triggered_count += 1

                    # Send notification to user
                    try:
                        message = (
                            f"🔔 <b>Алерт сработал!</b>\n\n"
                            f"{emoji} <b>{ticker}</b> {text}\n"
                            f"Целевая цена: <code>${target:.2f}</code>\n"
                            f"Текущая цена: <code>${ticker_price:.2f}</code>"
                        )
                        await bot.send_message(
                            chat_id=alert['user_id'],
                            text=message,
                            parse_mode="HTML"
                        )
                        logger.info(f"Alert triggered: {ticker} for user {alert['user_id']}")
                    except Exception as e:
                        logger.error(f"Failed to send alert to user {alert['user_id']}: {e}")

        if triggered_count > 0:
            logger.info(f"Processed {triggered_count} triggered alerts")

    except Exception as e:
        logger.error(f"Error checking alerts: {e}")
        if admin_id:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=f"❌ Ошибка проверки алертов: {e}"
                )
            except Exception:
                pass


def _fetch_prices(tickers: list) -> dict:
    """Fetch current prices for multiple tickers."""
    result = {}
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d")
            if not hist.empty:
                result[ticker] = float(hist['Close'].iloc[-1])
            else:
                result[ticker] = None
        except Exception as e:
            logger.error(f"Error fetching price for {ticker}: {e}")
            result[ticker] = None
    return result

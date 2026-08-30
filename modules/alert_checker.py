"""Background alert checker - runs every 5 minutes to check price alerts."""
import asyncio
import logging
import yfinance as yf
from modules import storage, smart_alerts

logger = logging.getLogger(__name__)


async def check_alerts(bot, admin_id: str = None):
    """Check all active alerts and notify users when triggered."""
    try:
        alerts = await storage.get_all_active_alerts()
        if not alerts:
            return

        # Separate price alerts and smart alerts
        price_alerts = [a for a in alerts if a.get('alert_type') == 'price']
        smart_alert_list = [a for a in alerts if a.get('alert_type') != 'price']

        # Check price alerts
        triggered_count = await _check_price_alerts(bot, price_alerts)

        # Check smart alerts
        triggered_count += await _check_smart_alerts(bot, smart_alert_list)

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


async def _check_price_alerts(bot, alerts: list) -> int:
    """Check price-based alerts."""
    if not alerts:
        return 0

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
                    logger.info(f"Price alert triggered: {ticker} for user {alert['user_id']}")
                except Exception as e:
                    logger.error(f"Failed to send alert to user {alert['user_id']}: {e}")

    return triggered_count


async def _check_smart_alerts(bot, alerts: list) -> int:
    """Check smart alerts (breakout, RSI, volume, etc.)."""
    if not alerts:
        return 0

    triggered_count = 0

    for alert in alerts:
        try:
            ticker = alert['ticker']
            alert_type = alert['alert_type']
            params = alert.get('params', {})

            result = await smart_alerts.check_smart_alert(alert_type, ticker, params)

            if result and result.get('triggered'):
                await storage.mark_alert_triggered(alert['id'])
                triggered_count += 1

                # Send notification to user
                try:
                    message = f"🔔 <b>Умный алерт сработал!</b>\n\n{result['message']}"
                    await bot.send_message(
                        chat_id=alert['user_id'],
                        text=message,
                        parse_mode="HTML"
                    )
                    logger.info(f"Smart alert triggered: {alert_type} {ticker} for user {alert['user_id']}")
                except Exception as e:
                    logger.error(f"Failed to send smart alert to user {alert['user_id']}: {e}")

        except Exception as e:
            logger.error(f"Error checking smart alert {alert.get('id')}: {e}")
            continue

    return triggered_count


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

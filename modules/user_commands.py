"""User commands for personal trading assistant features."""
import asyncio
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
import yfinance as yf

from modules import storage, charting

logger = logging.getLogger(__name__)


async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's portfolio with current P&L."""
    user_id = update.effective_user.id
    portfolio = await storage.get_portfolio(user_id)

    if not portfolio:
        keyboard = [
            [InlineKeyboardButton("➕ Добавить позицию", callback_data="portfolio_add")],
            [InlineKeyboardButton("📚 Инструкция", callback_data="portfolio_help")]
        ]
        await update.message.reply_text(
            "📊 <b>Ваш портфель пуст</b>\n\n"
            "Добавьте позицию командой:\n"
            "<code>/add TICKER количество цена</code>\n\n"
            "Пример: <code>/add AAPL 10 170.5</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Fetch current prices
    tickers = [p["ticker"] for p in portfolio]
    prices = await asyncio.to_thread(_fetch_prices, tickers)

    total_value = 0
    total_cost = 0
    lines = []

    for pos in portfolio:
        ticker = pos["ticker"]
        qty = pos["quantity"]
        avg_price = pos["avg_price"]
        current_price = prices.get(ticker, avg_price)

        position_value = qty * current_price
        position_cost = qty * avg_price
        pnl = position_value - position_cost
        pnl_pct = (pnl / position_cost * 100) if position_cost > 0 else 0

        total_value += position_value
        total_cost += position_cost

        emoji = "🟢" if pnl >= 0 else "🔴"
        lines.append(
            f"{emoji} <b>{ticker}</b> × {qty}\n"
            f"   Средняя: ${avg_price:.2f} → Текущая: ${current_price:.2f}\n"
            f"   P&L: <code>{pnl:+.2f}$</code> ({pnl_pct:+.1f}%)"
        )

    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    text = (
        f"📊 <b>Ваш портфель</b>\n\n"
        f"{''.join(lines)}\n\n"
        f"<b>Итого:</b>\n"
        f"Стоимость: <code>${total_value:,.2f}</code>\n"
        f"Вложено: <code>${total_cost:,.2f}</code>\n"
        f"P&L: <code>{total_pnl:+,.2f}$</code> ({total_pnl_pct:+.1f}%)"
    )

    keyboard = [
        [InlineKeyboardButton("➕ Добавить", callback_data="portfolio_add"),
         InlineKeyboardButton("➖ Удалить", callback_data="portfolio_remove")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="portfolio_refresh")]
    ]

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add position to portfolio: /add TICKER quantity price"""
    user_id = update.effective_user.id

    if len(context.args) < 3:
        await update.message.reply_text(
            "Использование: <code>/add TICKER количество цена</code>\n\n"
            "Пример: <code>/add AAPL 10 170.5</code>",
            parse_mode="HTML"
        )
        return

    try:
        ticker = context.args[0].upper()
        quantity = float(context.args[1])
        price = float(context.args[2])

        if quantity <= 0 or price <= 0:
            await update.message.reply_text("❌ Количество и цена должны быть положительными")
            return

        await storage.add_to_portfolio(user_id, ticker, quantity, price)
        await update.message.reply_text(
            f"✅ Добавлено в портфель:\n"
            f"<b>{ticker}</b> × {quantity} по ${price:.2f}",
            parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Используйте числа для количества и цены.")
    except Exception as e:
        logger.error(f"Error adding to portfolio: {e}")
        await update.message.reply_text("❌ Ошибка при добавлении позиции")


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove position from portfolio: /remove TICKER [quantity]"""
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text(
            "Использование: <code>/remove TICKER [количество]</code>\n\n"
            "Без количества — удалит всю позицию",
            parse_mode="HTML"
        )
        return

    try:
        ticker = context.args[0].upper()
        quantity = float(context.args[1]) if len(context.args) > 1 else None

        await storage.remove_from_portfolio(user_id, ticker, quantity)

        if quantity:
            await update.message.reply_text(f"✅ Удалено: <b>{ticker}</b> × {quantity}", parse_mode="HTML")
        else:
            await update.message.reply_text(f"✅ Позиция <b>{ticker}</b> полностью удалена", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error removing from portfolio: {e}")
        await update.message.reply_text("❌ Ошибка при удалении позиции")


async def cmd_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set price alert: /alert TICKER price"""
    user_id = update.effective_user.id

    if len(context.args) < 2:
        # Show existing alerts
        alerts = await storage.get_user_alerts(user_id)
        if not alerts:
            await update.message.reply_text(
                "🔔 <b>У вас нет активных алертов</b>\n\n"
                "Установите алерт командой:\n"
                "<code>/alert TICKER цена</code>\n\n"
                "Пример: <code>/alert AAPL 150</code>",
                parse_mode="HTML"
            )
            return

        lines = [
            f"• <b>{a['ticker']}</b> {'▲' if a['direction'] == 'above' else '▼'} ${a['target_price']:.2f} (ID: {a['id']})"
            for a in alerts
        ]
        text = "🔔 <b>Ваши алерты:</b>\n\n" + "\n".join(lines) + "\n\n<code>/delalert ID</code> — удалить"

        await update.message.reply_text(text, parse_mode="HTML")
        return

    try:
        ticker = context.args[0].upper()
        target_price = float(context.args[1])

        if target_price <= 0:
            await update.message.reply_text("❌ Цена должна быть положительной")
            return

        # Fetch current price to determine direction
        current_price = await asyncio.to_thread(_fetch_price, ticker)
        if current_price is None:
            await update.message.reply_text(f"❌ Не удалось получить цену для {ticker}")
            return

        direction = "above" if target_price > current_price else "below"

        await storage.add_alert(user_id, ticker, target_price, direction)

        emoji = "▲" if direction == "above" else "▼"
        await update.message.reply_text(
            f"✅ Алерт установлен:\n"
            f"<b>{ticker}</b> {emoji} ${target_price:.2f}\n"
            f"Текущая цена: ${current_price:.2f}",
            parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("❌ Неверный формат цены")
    except Exception as e:
        logger.error(f"Error setting alert: {e}")
        await update.message.reply_text("❌ Ошибка при установке алерта")


async def cmd_delalert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete alert: /delalert ID"""
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Использование: <code>/delalert ID</code>", parse_mode="HTML")
        return

    try:
        alert_id = int(context.args[0])
        await storage.delete_alert(user_id, alert_id)
        await update.message.reply_text("✅ Алерт удалён")
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом")
    except Exception as e:
        logger.error(f"Error deleting alert: {e}")
        await update.message.reply_text("❌ Ошибка при удалении алерта")


async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show watchlist or add tickers: /watch [TICKER1 TICKER2 ...]"""
    user_id = update.effective_user.id

    if not context.args:
        # Show watchlist
        watchlist = await storage.get_watchlist(user_id)
        if not watchlist:
            await update.message.reply_text(
                "👁 <b>Ваш watchlist пуст</b>\n\n"
                "Добавьте тикеры: <code>/watch AAPL MSFT TSLA</code>",
                parse_mode="HTML"
            )
            return

        # Fetch current prices
        prices = await asyncio.to_thread(_fetch_prices, watchlist)

        lines = []
        for ticker in watchlist:
            price = prices.get(ticker)
            if price:
                lines.append(f"• <b>{ticker}</b> — ${price:.2f}")
            else:
                lines.append(f"• <b>{ticker}</b> — н/д")

        text = "👁 <b>Ваш Watchlist:</b>\n\n" + "\n".join(lines)
        keyboard = [
            [InlineKeyboardButton("➕ Добавить", callback_data="watch_add"),
             InlineKeyboardButton("➖ Удалить", callback_data="watch_remove")],
            [InlineKeyboardButton("🔄 Обновить", callback_data="watch_refresh")]
        ]

        await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Add tickers to watchlist
    added = []
    for ticker in context.args:
        ticker = ticker.upper()
        await storage.add_to_watchlist(user_id, ticker)
        added.append(ticker)

    await update.message.reply_text(
        f"✅ Добавлено в watchlist: {', '.join(added)}",
        parse_mode="HTML"
    )


async def cmd_unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove ticker from watchlist: /unwatch TICKER"""
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Использование: <code>/unwatch TICKER</code>", parse_mode="HTML")
        return

    ticker = context.args[0].upper()
    await storage.remove_from_watchlist(user_id, ticker)
    await update.message.reply_text(f"✅ <b>{ticker}</b> удалён из watchlist", parse_mode="HTML")


async def cmd_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get chart for ticker: /chart TICKER"""
    if not context.args:
        await update.message.reply_text("Использование: <code>/chart TICKER</code>", parse_mode="HTML")
        return

    ticker = context.args[0].upper()

    try:
        image = await asyncio.to_thread(charting.build_chart, ticker)
        if image:
            await update.message.reply_photo(
                photo=image,
                caption=f"<b>{ticker}</b> · график TRIADA INVESTING",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text("❌ Не удалось построить график")
    except Exception as e:
        logger.error(f"Error building chart: {e}")
        await update.message.reply_text("❌ Ошибка при построении графика")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get quick stats for ticker: /stats TICKER"""
    if not context.args:
        await update.message.reply_text("Использование: <code>/stats TICKER</code>", parse_mode="HTML")
        return

    ticker = context.args[0].upper()

    try:
        data = await asyncio.to_thread(_fetch_ticker_info, ticker)
        if not data:
            await update.message.reply_text(f"❌ Не удалось получить данные для {ticker}")
            return

        text = (
            f"📊 <b>{data['name']}</b> ({ticker})\n\n"
            f"Цена: <code>${data['price']:.2f}</code>\n"
            f"Изменение: <code>{data['change']:+.2f}%</code>\n\n"
            f"Market Cap: <code>${data['market_cap']}</code>\n"
            f"P/E: <code>{data['pe']}</code>\n"
            f"Volume: <code>{data['volume']}</code>\n"
            f"52W Range: <code>${data['low_52w']:.2f} — ${data['high_52w']:.2f}</code>"
        )

        keyboard = [[InlineKeyboardButton("📈 График", callback_data=f"chart_{ticker}")]]

        await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        await update.message.reply_text("❌ Ошибка при получении данных")


# ─── Helper Functions ─────────────────────────────────────────────────────────

def _fetch_price(ticker: str) -> float | None:
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        if hist.empty:
            return None
        return float(hist['Close'].iloc[-1])
    except Exception:
        return None


def _fetch_prices(tickers: list) -> dict:
    result = {}
    for ticker in tickers:
        price = _fetch_price(ticker)
        if price:
            result[ticker] = price
    return result


def _fetch_ticker_info(ticker: str) -> dict | None:
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="1d")

        if hist.empty:
            return None

        current_price = float(hist['Close'].iloc[-1])
        prev_close = info.get('previousClose', current_price)
        change = ((current_price - prev_close) / prev_close * 100) if prev_close else 0

        market_cap = info.get('marketCap', 0)
        if market_cap >= 1e12:
            mc_str = f"{market_cap/1e12:.2f}T"
        elif market_cap >= 1e9:
            mc_str = f"{market_cap/1e9:.2f}B"
        elif market_cap >= 1e6:
            mc_str = f"{market_cap/1e6:.2f}M"
        else:
            mc_str = "н/д"

        volume = info.get('volume', 0)
        if volume >= 1e9:
            vol_str = f"{volume/1e9:.2f}B"
        elif volume >= 1e6:
            vol_str = f"{volume/1e6:.2f}M"
        else:
            vol_str = f"{volume:,}"

        return {
            'name': info.get('shortName', ticker),
            'price': current_price,
            'change': change,
            'market_cap': mc_str,
            'pe': info.get('trailingPE', 'н/д'),
            'volume': vol_str,
            'low_52w': info.get('fiftyTwoWeekLow', 0),
            'high_52w': info.get('fiftyTwoWeekHigh', 0),
        }
    except Exception as e:
        logger.error(f"Error fetching ticker info: {e}")
        return None


async def cmd_smartalert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set smart alert: /smartalert TICKER type [params]

    Types:
    - breakout LEVEL - пробой вверх
    - breakdown LEVEL - пробой вниз
    - rsi_oversold - RSI < 30
    - rsi_overbought - RSI > 70
    - volume_spike - объем > 2x средний
    - golden_cross - 50 SMA > 200 SMA
    - death_cross - 50 SMA < 200 SMA
    """
    user_id = update.effective_user.id

    if len(context.args) < 2:
        await update.message.reply_text(
            "🔔 <b>Умные алерты</b>\n\n"
            "Использование: <code>/smartalert TICKER тип [параметры]</code>\n\n"
            "<b>Доступные типы:</b>\n"
            "• <code>breakout LEVEL</code> — пробой вверх\n"
            "• <code>breakdown LEVEL</code> — пробой вниз\n"
            "• <code>rsi_oversold</code> — RSI < 30\n"
            "• <code>rsi_overbought</code> — RSI > 70\n"
            "• <code>volume_spike</code> — объем > 2x средний\n"
            "• <code>golden_cross</code> — 50 SMA > 200 SMA\n"
            "• <code>death_cross</code> — 50 SMA < 200 SMA\n\n"
            "<b>Примеры:</b>\n"
            "<code>/smartalert AAPL breakout 180</code>\n"
            "<code>/smartalert TSLA rsi_oversold</code>\n"
            "<code>/smartalert SPY golden_cross</code>",
            parse_mode="HTML"
        )
        return

    try:
        ticker = context.args[0].upper()
        alert_type = context.args[1].lower()

        params = {}

        # Parse parameters based on alert type
        if alert_type in ["breakout", "breakdown"]:
            if len(context.args) < 3:
                await update.message.reply_text(f"❌ Укажите уровень для {alert_type}")
                return
            params["level"] = float(context.args[2])

        # Validate alert type
        valid_types = ["breakout", "breakdown", "rsi_oversold", "rsi_overbought",
                      "volume_spike", "golden_cross", "death_cross"]
        if alert_type not in valid_types:
            await update.message.reply_text(f"❌ Неизвестный тип алерта: {alert_type}")
            return

        await storage.add_smart_alert(user_id, ticker, alert_type, params)

        # Format message
        type_names = {
            "breakout": f"🚀 Пробой ${params.get('level', 0):.2f}",
            "breakdown": f"📉 Пробой вниз ${params.get('level', 0):.2f}",
            "rsi_oversold": "📊 RSI перепродан (<30)",
            "rsi_overbought": "📊 RSI перекуплен (>70)",
            "volume_spike": "💥 Всплеск объема (>2x)",
            "golden_cross": "✨ Golden Cross (50>200 SMA)",
            "death_cross": "💀 Death Cross (50<200 SMA)",
        }

        await update.message.reply_text(
            f"✅ <b>Умный алерт установлен:</b>\n\n"
            f"<b>{ticker}</b>\n"
            f"{type_names.get(alert_type, alert_type)}\n\n"
            f"Проверяется каждые 5 минут",
            parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("❌ Неверный формат параметров")
    except Exception as e:
        logger.error(f"Error setting smart alert: {e}")
        await update.message.reply_text("❌ Ошибка при установке алерта")


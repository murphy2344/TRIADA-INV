import asyncio
import html
import io
import logging
import os
import threading
import uuid
from datetime import datetime

import pytz
from flask import Flask, render_template_string
from telegram import Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes

from config.config import BOT_TOKEN, ADMIN_USERNAME, ADMIN_ID, CHANNEL_ID, GROUP_CHAT_ID
from modules import pipeline, storage, dedup, forum_topics, telegram_monitor, user_commands, bot_commands
from modules.scheduler import build_scheduler
from modules.telegram_sender import notify_admin

logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)
MSK = pytz.timezone("Europe/Moscow")

BOT_START_TIME = datetime.now()
application = None
scheduler = None

# ─── Flask dashboard ──────────────────────────────────────────────────────────
flask_app = Flask(__name__)

DASHBOARD_HTML = """
<!DOCTYPE html><html><head><title>TRIADA INVESTING Bot</title>
<meta http-equiv="refresh" content="30">
<style>
body{background:#0d1117;color:#e6edf3;font-family:'Segoe UI',sans-serif;padding:24px;margin:0}
h1{color:#58a6ff;margin-bottom:4px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:16px}
.ok{color:#3fb950} .err{color:#f85149} .warn{color:#d29922}
pre{background:#010409;padding:12px;border-radius:6px;color:#f85149;font-size:12px;overflow-x:auto}
</style></head><body>
<div class="card"><h1>📊 TRIADA INVESTING Bot Console</h1>
<p>Статус: <span class="ok"><b>РАБОТАЕТ</b></span></p>
<p>Аптайм: <b>{{ uptime }}</b></p>
<p>Постов сегодня: <b>{{ posts }}</b></p>
<p>Канал: <code>{{ channel }}</code></p>
</div>
<div class="card"><h2>Модули</h2>
<p>✅ AI: Gemini gemini-2.5-flash (fallback: Groq)</p>
<p>✅ AI-критик: Gemini (fallback: Groq, только high-impact BREAKING)</p>
<p>✅ Графики: Finviz (с детектом заглушки) → yfinance+matplotlib (fallback)</p>
<p>✅ Фото: стаб-файлы из assets/stubs/ / RSS→Wikimedia→Google CSE→Pexels</p>
<p>✅ Антидубль: Upstash Redis → SQLite (fallback), 2 уровня проверки</p>
<p>✅ Трек-рекорд: проверка через 24ч + публикация результата в канал</p>
<p>✅ COT: позиции крупных игроков (CFTC, по пятницам)</p>
<p>✅ 13F: отчёты крупных фондов (SEC EDGAR, по понедельникам)</p>
<p>✅ Планировщик: misfire_grace_time=600с, coalesce=True</p>
</div>
</body></html>
"""

@flask_app.route("/")
def dashboard():
  uptime = str(datetime.now() - BOT_START_TIME).split(".")[0]
  stats = {}
  try:
      import asyncio as _a
      loop = _a.new_event_loop()
      stats = loop.run_until_complete(storage.get_today_stats())
      loop.close()
  except Exception:
      stats = {"posts": "?", "errors": "?"}
  return render_template_string(
      DASHBOARD_HTML,
      uptime=uptime,
      posts=stats.get("posts", 0),
      channel=CHANNEL_ID
  )

@flask_app.route("/health")
def health():
  return {"status": "ok", "uptime": str(datetime.now() - BOT_START_TIME).split(".")[0]}, 200

def run_flask():
  port = int(os.environ.get("PORT", 5000))
  flask_app.run(host="0.0.0.0", port=port, use_reloader=False)


# ─── Admin guard ──────────────────────────────────────────────────────────────
def admin_only(func):
  async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
      # Check if admin verification was already done (e.g., in callback handler)
      if context.bot_data.get("_skip_admin_check"):
          return await func(update, context)

      user = update.effective_user
      if not user:
          return
      is_admin = (user.username == ADMIN_USERNAME) or (str(user.id) == str(ADMIN_ID))
      if not is_admin:
          admin_id = context.bot_data.get("admin_id", ADMIN_ID)
          if admin_id:
              await notify_admin(
                  context.bot, admin_id,
                  f"⚠️ Попытка управления от id{user.id}|@{user.username or 'unknown'}"
              )
          return
      context.bot_data["admin_id"] = str(update.effective_chat.id)
      return await func(update, context)
  return wrapper


# ─── Commands ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user = update.effective_user
  is_admin = (user.username == ADMIN_USERNAME) or (str(user.id) == str(ADMIN_ID))

  # Debug logging
  logger.info(f"User {user.id} (@{user.username}) - is_admin: {is_admin}, ADMIN_USERNAME: {ADMIN_USERNAME}, ADMIN_ID: {ADMIN_ID}")

  if is_admin:
      text = (
          "🤖 <b>TRIADA INVESTING Bot — Admin Panel</b>\n\n"
          "<b>📊 Персональные команды:</b>\n"
          "/portfolio — ваш портфель\n"
          "/add TICKER кол-во цена — добавить позицию\n"
          "/remove TICKER — удалить позицию\n"
          "/analyze — анализ портфеля (риски, диверсификация)\n"
          "/compare AAPL MSFT GOOGL — сравнить тикеры\n"
          "/backtest buy AAPL 2020-01-01 10000 — бэктест сделки\n"
          "/news — новости по вашему watchlist\n"
          "/ideas — AI торговые идеи (персональные)\n"
          "/fundamentals AAPL — фундаментальный анализ\n"
          "/peers TSLA — сравнение с конкурентами\n"
          "/analysts NVDA — мнение аналитиков\n"
          "/alert TICKER цена — установить алерт\n"
          "/smartalert — умный алерт (breakout, RSI, volume)\n"
          "/delalert ID — удалить алерт\n"
          "/watch — показать watchlist\n"
          "/unwatch TICKER — удалить из watchlist\n"
          "/chart TICKER — график\n"
          "/stats TICKER — статистика\n\n"
          "<b>🔧 Служебные команды:</b>\n"
          "Используйте кнопки ниже ↓"
      )

      # Admin control buttons
      from telegram import InlineKeyboardButton, InlineKeyboardMarkup
      keyboard = [
          [InlineKeyboardButton("📊 Статус", callback_data="admin_status"),
           InlineKeyboardButton("🧪 Тест", callback_data="admin_test")],
          [InlineKeyboardButton("🔥 Breaking", callback_data="admin_breaking"),
           InlineKeyboardButton("⏰ Hourly", callback_data="admin_hourly")],
          [InlineKeyboardButton("🌅 Morning", callback_data="admin_morning"),
           InlineKeyboardButton("🌆 Evening", callback_data="admin_evening")],
          [InlineKeyboardButton("📅 Weekly", callback_data="admin_weekly"),
           InlineKeyboardButton("📆 Monthly", callback_data="admin_monthly")],
          [InlineKeyboardButton("🏆 Leaders", callback_data="admin_leaders"),
           InlineKeyboardButton("💹 Pulse", callback_data="admin_pulse")],
          [InlineKeyboardButton("📈 Earnings", callback_data="admin_earnings"),
           InlineKeyboardButton("📅 Calendar", callback_data="admin_calendar")],
          [InlineKeyboardButton("🔔 Alerts", callback_data="admin_alerts"),
           InlineKeyboardButton("🗺 Heatmap", callback_data="admin_heatmap")],
          [InlineKeyboardButton("📊 COT", callback_data="admin_cot"),
           InlineKeyboardButton("💼 13F", callback_data="admin_13f")],
          [InlineKeyboardButton("🌡 Sentiment", callback_data="admin_sentiment"),
           InlineKeyboardButton("📊 Sectors", callback_data="admin_sectors")],
          [InlineKeyboardButton("🔍 Snapshot", callback_data="admin_snapshot"),
           InlineKeyboardButton("📡 Screener", callback_data="admin_screener")],
          [InlineKeyboardButton("📺 Каналы", callback_data="admin_channels")],
      ]

      await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
  else:
      text = (
          "👋 <b>Добро пожаловать в TRIADA INVESTING Bot!</b>\n\n"
          "🎯 <b>Ваш личный трейдинг-терминал в Telegram</b>\n\n"
          "💡 Все инструменты для анализа рынка в одном месте:\n"
          "• Фундаментальный анализ компаний\n"
          "• AI торговые идеи и сигналы\n"
          "• Управление портфелем и алерты\n"
          "• Новости и аналитика в реальном времени\n\n"
          "👇 <b>Выберите действие:</b>"
      )

      # User interactive buttons
      from telegram import InlineKeyboardButton, InlineKeyboardMarkup
      keyboard = [
          [InlineKeyboardButton("📊 Мой портфель", callback_data="user_portfolio"),
           InlineKeyboardButton("💡 AI Идеи", callback_data="user_ideas")],
          [InlineKeyboardButton("🔍 Анализ компании", callback_data="user_fundamentals"),
           InlineKeyboardButton("📈 Графики", callback_data="user_charts")],
          [InlineKeyboardButton("🔔 Алерты", callback_data="user_alerts"),
           InlineKeyboardButton("👁 Watchlist", callback_data="user_watchlist")],
          [InlineKeyboardButton("📰 Новости", callback_data="user_news"),
           InlineKeyboardButton("🎯 Сравнить акции", callback_data="user_compare")],
          [InlineKeyboardButton("📚 Инструкция", callback_data="user_help"),
           InlineKeyboardButton("💬 Обратная связь", callback_data="user_feedback")],
      ]

      await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


@admin_only
async def cmd_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
  channels = await telegram_monitor.get_watchlist()
  if not channels:
      text = (
          "📡 Список каналов пуст.\n"
          "Добавьте публичный канал: /addchannel @channel"
      )
  else:
      text = "📡 <b>Каналы мониторинга:</b>\n" + "\n".join(
          f"• @{channel}" for channel in channels
      )
  await update.message.reply_text(text, parse_mode="HTML")


@admin_only
async def cmd_addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
  value = " ".join(context.args).strip()
  if not value:
      await update.message.reply_text(
          "Использование: /addchannel @channel\n"
          "Также можно отправить публичную ссылку https://t.me/channel"
      )
      return
  ok, message = await telegram_monitor.add_channel(value)
  await update.message.reply_text(("✅ " if ok else "⚠️ ") + message)


@admin_only
async def cmd_removechannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
  value = " ".join(context.args).strip()
  if not value:
      await update.message.reply_text("Использование: /removechannel @channel")
      return
  ok, message = await telegram_monitor.remove_channel(value)
  await update.message.reply_text(("✅ " if ok else "⚠️ ") + message)


@admin_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
  uptime = str(datetime.now() - BOT_START_TIME).split(".")[0]
  stats = await storage.get_today_stats()
  accuracy = await storage.get_accuracy_stats(days=7)

  next_jobs = []
  if scheduler:
      for job in scheduler.get_jobs():
          nxt = job.next_run_time
          if nxt:
              msk_time = nxt.astimezone(MSK).strftime("%H:%M МСК")
              next_jobs.append(f"  • {job.id}: {msk_time}")
  next_str = "\n".join(next_jobs[:8]) if next_jobs else "нет данных"

  if accuracy["total"] > 0:
      accuracy_line = (
          f"🎯 Точность рекомендаций (7 дней): "
          f"<b>{accuracy['accuracy_pct']}%</b> ({accuracy['correct']}/{accuracy['total']})"
      )
  else:
      accuracy_line = "🎯 Точность рекомендаций: пока нет проверенных данных"

  text = (
      f"📊 <b>Статус TRIADA INVESTING Bot</b>\n\n"
      f"⏱ Аптайм: <b>{uptime}</b>\n"
      f"📰 Постов сегодня: <b>{stats['posts']}</b>\n"
      f"❌ Ошибок сегодня: <b>{stats['errors']}</b>\n"
      f"{accuracy_line}\n\n"
      f"<b>Следующие задачи:</b>\n{next_str}"
  )
  await update.message.reply_text(text, parse_mode="HTML")


@admin_only
async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("🧪 Запускаю тест (breaking → hourly), подождите...")
  admin_id = str(update.effective_chat.id)
  try:
      posted = await pipeline.run_breaking(context.bot, admin_id)
      if posted == 0:
          posted = await pipeline.run_hourly(context.bot, admin_id)
      if posted > 0:
          await update.message.reply_text(f"✅ Тест выполнен, опубликовано: {posted}")
      else:
          await update.message.reply_text(
              "❌ Нет новых новостей или ошибка AI.\n"
               "Проверьте GEMINI_API_KEY/GOOGLE_API_KEY или GROQ_API_KEY и подключение к RSS."
          )
  except Exception as e:
      await update.message.reply_text(f"❌ Тест не удался: {e}")


@admin_only
async def cmd_breaking(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("⚡ Проверяю срочные новости...")
  admin_id = str(update.effective_chat.id)
  try:
      posted = await pipeline.run_breaking(context.bot, admin_id)
      await update.message.reply_text(
          f"✅ Срочные: опубликовано {posted}" if posted > 0
          else "ℹ️ Нет новых срочных новостей."
      )
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка: {e}")


@admin_only
async def cmd_hourly(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("📰 Формирую часовой дайджест...")
  admin_id = str(update.effective_chat.id)
  try:
      posted = await pipeline.run_hourly(context.bot, admin_id)
      await update.message.reply_text(
          "✅ Часовой дайджест опубликован." if posted > 0
          else "ℹ️ Нет новых новостей для часового поста."
      )
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка: {e}")


@admin_only
async def cmd_morning(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("🌅 Формирую утренний обзор...")
  admin_id = str(update.effective_chat.id)
  try:
      posted = await pipeline.run_morning(context.bot, admin_id)
      await update.message.reply_text(
          "✅ Утренний обзор опубликован." if posted > 0
          else "❌ Не удалось опубликовать."
      )
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка: {e}")


@admin_only
async def cmd_evening(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("🌆 Формирую вечерний обзор...")
  admin_id = str(update.effective_chat.id)
  try:
      posted = await pipeline.run_evening(context.bot, admin_id)
      await update.message.reply_text(
          "✅ Вечерний обзор опубликован." if posted > 0
          else "❌ Не удалось опубликовать."
      )
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка: {e}")


@admin_only
async def cmd_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("📅 Формирую недельный итог...")
  admin_id = str(update.effective_chat.id)
  try:
      posted = await pipeline.run_weekly(context.bot, admin_id)
      await update.message.reply_text(
          "✅ Недельный итог опубликован." if posted > 0
          else "❌ Не удалось опубликовать."
      )
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка: {e}")


@admin_only
async def cmd_monthly(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("📆 Формирую месячный итог...")
  admin_id = str(update.effective_chat.id)
  try:
      posted = await pipeline.run_monthly(context.bot, admin_id)
      await update.message.reply_text(
          "✅ Месячный итог опубликован." if posted > 0
          else "❌ Не удалось опубликовать."
      )
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка: {e}")


@admin_only
async def cmd_leaders(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("📊 Собираю лидеров мирового рынка, подождите...")
  admin_id = str(update.effective_chat.id)
  try:
      posted = await pipeline.run_leaders(context.bot, admin_id)
      await update.message.reply_text(
          "✅ Лидеры рынка опубликованы." if posted > 0
          else "❌ Нет данных (возможно, рынок закрыт)."
      )
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка: {e}")


@admin_only
async def cmd_pulse(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("📌 Обновляю пульс рынка...")
  admin_id = str(update.effective_chat.id)
  try:
      ok = await pipeline.update_market_pulse(context.bot, admin_id)
      await update.message.reply_text(
          "✅ Пульс рынка обновлён." if ok
          else "❌ Не удалось обновить (данные недоступны)."
      )
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка: {e}")


@admin_only
async def cmd_earnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("💹 Собираю дайджест отчётностей...")
  admin_id = str(update.effective_chat.id)
  try:
      posted = await pipeline.run_earnings_digest(context.bot, admin_id)
      await update.message.reply_text(
          f"✅ Опубликовано постов: {posted}." if posted > 0
          else "ℹ️ Нет актуальных отчётностей."
      )
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка: {e}")


@admin_only
async def cmd_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("🗓 Загружаю экономический календарь...")
  admin_id = str(update.effective_chat.id)
  try:
      posted = await pipeline.run_econ_calendar_today(context.bot, admin_id)
      posted += await pipeline.run_econ_calendar_weekly(context.bot, admin_id)
      await update.message.reply_text(
          f"✅ Опубликовано постов: {posted}." if posted > 0
          else "ℹ️ Нет событий в календаре (проверьте FRED_API_KEY)."
      )
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка: {e}")


@admin_only
async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("📡 Проверяю технические алерты (RSI / SMA)...")
  admin_id = str(update.effective_chat.id)
  try:
      posted = await pipeline.run_technical_alerts(context.bot, admin_id)
      await update.message.reply_text(
          f"✅ Опубликовано алертов: {posted}." if posted > 0
          else "ℹ️ Нет активных сигналов."
      )
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка: {e}")


@admin_only
async def cmd_heatmap(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("🌡 Генерирую тепловую карту секторов...")
  admin_id = str(update.effective_chat.id)
  try:
      posted = await pipeline.run_sector_heatmap(context.bot, admin_id)
      await update.message.reply_text(
          "✅ Тепловая карта опубликована." if posted > 0
          else "❌ Не удалось получить данные."
      )
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка: {e}")


@admin_only
async def cmd_cot(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("📊 Загружаю позиции крупных игроков (COT/CFTC)...")
  admin_id = str(update.effective_chat.id)
  try:
      posted = await pipeline.run_cot_report(context.bot, admin_id)
      await update.message.reply_text(
          "✅ COT Report опубликован." if posted > 0
          else "❌ Не удалось получить данные CFTC."
      )
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка: {e}")


@admin_only
async def cmd_13f(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("🏦 Загружаю 13F отчёты крупных фондов (SEC EDGAR)...")
  admin_id = str(update.effective_chat.id)
  try:
      posted = await pipeline.run_13f_digest(context.bot, admin_id)
      await update.message.reply_text(
          "✅ 13F Digest опубликован." if posted > 0
          else "❌ Не удалось получить данные SEC."
      )
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка: {e}")


@admin_only
async def cmd_testall(update: Update, context: ContextTypes.DEFAULT_TYPE):
  """Полная диагностика — проверяет все модули и публикует отчёт в чат + канал."""
  admin_id = str(update.effective_chat.id)
  await update.message.reply_text(
      "🔍 <b>Запускаю полную диагностику...</b>\n\n"
      "Это займёт 1–3 минуты — проверяю RSS, AI, графики, БД, COT, 13F и т.д.\n"
      "Результат придёт сюда и будет опубликован в канал.",
      parse_mode="HTML"
  )
  try:
      from modules import selftest
      report = await selftest.run_full_selftest(context.bot, admin_id, scheduler)
      # Отправляем в чат с администратором
      await context.bot.send_message(chat_id=admin_id, text=report, parse_mode="HTML")
      # Публикуем в канал чтобы владелец видел
      from config.config import CHANNEL_ID
      try:
          await context.bot.send_message(
              chat_id=CHANNEL_ID,
              text=report,
              parse_mode="HTML"
          )
      except Exception as e_ch:
          await update.message.reply_text(f"⚠️ В канал не отправилось: {e_ch}")
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка диагностики: {e}")


@admin_only
async def cmd_snapshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
  """Market snapshot — обзор рынков."""
  await update.message.reply_text("📊 Собираю market snapshot...")
  admin_id = str(update.effective_chat.id)
  try:
      posted = await pipeline.run_market_snapshot(context.bot, admin_id)
      await update.message.reply_text(
          "✅ Market snapshot опубликован." if posted > 0
          else "❌ Не удалось получить данные."
      )
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка: {e}")


@admin_only
async def cmd_screener(update: Update, context: ContextTypes.DEFAULT_TYPE):
  """Screener — breakouts и top movers."""
  await update.message.reply_text("🔍 Запускаю screener...")
  admin_id = str(update.effective_chat.id)
  try:
      posted = 0
      posted += await pipeline.run_screener_breakouts(context.bot, admin_id)
      posted += await pipeline.run_screener_top_movers(context.bot, admin_id)
      await update.message.reply_text(
          f"✅ Screener завершен, опубликовано: {posted}" if posted > 0
          else "ℹ️ Нет интересных сигналов."
      )
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка: {e}")


@admin_only
async def cmd_sentiment(update: Update, context: ContextTypes.DEFAULT_TYPE):
  """Fear & Greed Dashboard — индикаторы настроения."""
  await update.message.reply_text("📊 Собираю индикаторы настроения...")
  admin_id = str(update.effective_chat.id)
  try:
      posted = await pipeline.run_fear_greed_dashboard(context.bot, admin_id)
      await update.message.reply_text(
          "✅ Fear & Greed Dashboard опубликован." if posted > 0
          else "❌ Не удалось получить данные."
      )
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка: {e}")


@admin_only
async def cmd_sectors(update: Update, context: ContextTypes.DEFAULT_TYPE):
  """Sector Performance — какие секторы лидируют."""
  await update.message.reply_text("📊 Анализирую секторы...")
  admin_id = str(update.effective_chat.id)
  try:
      posted = await pipeline.run_sector_performance(context.bot, admin_id)
      await update.message.reply_text(
          "✅ Sector Performance опубликован." if posted > 0
          else "❌ Не удалось получить данные."
      )
  except Exception as e:
      await update.message.reply_text(f"❌ Ошибка: {e}")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
  """Handle the small set of buttons attached to analytical posts."""
  query = update.callback_query
  if not query:
      return
  data = query.data or ""
  user = query.from_user

  # User button handlers
  if data.startswith("user_"):
      await query.answer()

      if data == "user_portfolio":
          await query.message.reply_text(
              "📊 <b>Управление портфелем</b>\n\n"
              "<b>Просмотр:</b>\n"
              "/portfolio — показать портфель\n"
              "/analyze — анализ (риски, диверсификация)\n\n"
              "<b>Добавление позиций:</b>\n"
              "/add TICKER количество цена\n"
              "Пример: <code>/add AAPL 10 170.5</code>\n\n"
              "<b>Удаление:</b>\n"
              "/remove TICKER",
              parse_mode="HTML"
          )
          return

      if data == "user_ideas":
          await query.message.reply_text(
              "💡 <b>AI Торговые идеи</b>\n\n"
              "Команда: /ideas\n\n"
              "Показывает персональные торговые идеи на основе:\n"
              "• Вашего портфеля\n"
              "• Вашего watchlist\n"
              "• Технического анализа (RSI, SMA, momentum)\n"
              "• Оценки (P/E, рост, волатильность)\n\n"
              "Сигналы: BUY, SELL, WATCH, NEUTRAL",
              parse_mode="HTML"
          )
          return

      if data == "user_fundamentals":
          await query.message.reply_text(
              "🔍 <b>Фундаментальный анализ</b>\n\n"
              "<b>Финансовые отчёты компании:</b>\n"
              "/fundamentals TICKER\n"
              "Пример: <code>/fundamentals AAPL</code>\n\n"
              "<b>Сравнение с конкурентами:</b>\n"
              "/peers TICKER\n"
              "Пример: <code>/peers TSLA</code>\n\n"
              "<b>Мнение аналитиков Wall Street:</b>\n"
              "/analysts TICKER\n"
              "Пример: <code>/analysts NVDA</code>\n\n"
              "💡 Используйте эти команды для принятия решений о покупке/продаже",
              parse_mode="HTML"
          )
          return

      if data == "user_charts":
          await query.message.reply_text(
              "📈 <b>Графики и статистика</b>\n\n"
              "<b>График тикера:</b>\n"
              "/chart TICKER\n"
              "Пример: <code>/chart AAPL</code>\n\n"
              "<b>Быстрая статистика:</b>\n"
              "/stats TICKER\n"
              "Пример: <code>/stats TSLA</code>\n\n"
              "<b>Бэктестинг сделки:</b>\n"
              "/backtest action TICKER дата сумма\n"
              "Пример: <code>/backtest buy AAPL 2020-01-01 10000</code>",
              parse_mode="HTML"
          )
          return

      if data == "user_alerts":
          await query.message.reply_text(
              "🔔 <b>Система алертов</b>\n\n"
              "<b>Ценовой алерт:</b>\n"
              "/alert TICKER цена\n"
              "Пример: <code>/alert AAPL 180</code>\n\n"
              "<b>Умные алерты (technical):</b>\n"
              "/smartalert TICKER тип порог\n"
              "Типы: breakout, rsi_oversold, rsi_overbought, volume_spike\n"
              "Пример: <code>/smartalert TSLA breakout 200</code>\n\n"
              "<b>Удалить алерт:</b>\n"
              "/delalert ID",
              parse_mode="HTML"
          )
          return

      if data == "user_watchlist":
          await query.message.reply_text(
              "👁 <b>Watchlist</b>\n\n"
              "<b>Просмотр списка:</b>\n"
              "/watch\n\n"
              "<b>Добавить тикеры:</b>\n"
              "/watch TICKER1 TICKER2 TICKER3\n"
              "Пример: <code>/watch AAPL MSFT GOOGL</code>\n\n"
              "<b>Удалить из списка:</b>\n"
              "/unwatch TICKER\n"
              "Пример: <code>/unwatch AAPL</code>\n\n"
              "<b>Новости по watchlist:</b>\n"
              "/news — показывает последние новости по вашим тикерам",
              parse_mode="HTML"
          )
          return

      if data == "user_news":
          await query.message.reply_text(
              "📰 <b>Новости</b>\n\n"
              "<b>Новости по вашему watchlist:</b>\n"
              "/news — последние новости по вашим тикерам\n\n"
              "💡 Сначала добавьте тикеры в watchlist командой:\n"
              "<code>/watch AAPL TSLA NVDA</code>\n\n"
              "Также подписывайтесь на канал для:\n"
              "• Срочных новостей (breaking)\n"
              "• Часовых дайджестов\n"
              "• Утренних и вечерних обзоров\n"
              "• Earnings календаря",
              parse_mode="HTML"
          )
          return

      if data == "user_compare":
          await query.message.reply_text(
              "🎯 <b>Сравнение акций</b>\n\n"
              "<b>Сравнить несколько тикеров:</b>\n"
              "/compare TICKER1 TICKER2 TICKER3\n"
              "Пример: <code>/compare AAPL MSFT GOOGL</code>\n\n"
              "Показывает:\n"
              "• Оценку (P/E, P/S, P/B)\n"
              "• Рост (1M, 3M, 6M, 1Y)\n"
              "• Размер (Market Cap)\n"
              "• Волатильность (Beta)\n"
              "• Корреляцию движения цен\n\n"
              "Можно сравнить от 2 до 5 тикеров",
              parse_mode="HTML"
          )
          return

      if data == "user_help":
          await query.message.reply_text(
              "📚 <b>Полная инструкция</b>\n\n"
              "<b>🎯 Быстрый старт для новичков:</b>\n\n"
              "1️⃣ <b>Анализ компании</b>\n"
              "   /fundamentals AAPL — финансовые отчёты\n"
              "   /analysts AAPL — что говорят аналитики\n"
              "   /chart AAPL — посмотреть график\n\n"
              "2️⃣ <b>Создать watchlist</b>\n"
              "   /watch AAPL TSLA NVDA — добавить тикеры\n"
              "   /news — читать новости по ним\n\n"
              "3️⃣ <b>Добавить портфель</b>\n"
              "   /add AAPL 10 170.5 — купили 10 акций\n"
              "   /portfolio — посмотреть P&L\n"
              "   /ideas — получить AI рекомендации\n\n"
              "4️⃣ <b>Настроить алерты</b>\n"
              "   /alert AAPL 200 — уведомление при $200\n\n"
              "<b>💡 Совет:</b> Начните с команды /fundamentals для любой интересной акции!\n\n"
              "Для подробной справки по каждой функции нажимайте кнопки в главном меню.",
              parse_mode="HTML"
          )
          return

      if data == "user_feedback":
          await query.message.reply_text(
              "💬 <b>Обратная связь</b>\n\n"
              "Мы постоянно улучшаем бота и добавляем новые функции!\n\n"
              "<b>Хотите что-то предложить?</b>\n"
              "Напишите ваши идеи, пожелания или найденные баги:\n\n"
              "📧 Просто напишите сообщение здесь в чате, начиная со слова <b>ИДЕЯ</b>\n\n"
              "Пример:\n"
              "<code>ИДЕЯ: Добавьте анализ опционов</code>\n\n"
              "Мы читаем все сообщения и реализуем лучшие идеи! 🚀",
              parse_mode="HTML"
          )
          return
      return

  # Admin button handlers
  if data.startswith("admin_"):
      # Check if user is admin
      logger.info(f"Admin button pressed by user.id={user.id}, user.username={user.username}")
      logger.info(f"Config: ADMIN_ID={ADMIN_ID}, ADMIN_USERNAME={ADMIN_USERNAME}")
      is_admin = (user.username == ADMIN_USERNAME) or (str(user.id) == str(ADMIN_ID))
      logger.info(f"is_admin={is_admin}")
      if not is_admin:
          await query.answer("❌ Доступно только администратору", show_alert=True)
          return

      await query.answer()
      admin_id = str(user.id)

      # Map callbacks to command handlers
      handlers_map = {
          "admin_status": (cmd_status, "📊 Получаю статус..."),
          "admin_test": (cmd_test, "🧪 Запускаю тест..."),
          "admin_breaking": (cmd_breaking, "⚡ Проверяю срочные новости..."),
          "admin_hourly": (cmd_hourly, "📰 Формирую часовой дайджест..."),
          "admin_morning": (cmd_morning, "🌅 Формирую утренний обзор..."),
          "admin_evening": (cmd_evening, "🌆 Формирую вечерний обзор..."),
          "admin_weekly": (cmd_weekly, "📅 Формирую недельный итог..."),
          "admin_monthly": (cmd_monthly, "📆 Формирую месячный итог..."),
          "admin_leaders": (cmd_leaders, "🏆 Собираю лидеров рынка..."),
          "admin_pulse": (cmd_pulse, "💹 Обновляю пульс рынка..."),
          "admin_earnings": (cmd_earnings, "💹 Собираю дайджест отчётностей..."),
          "admin_calendar": (cmd_calendar, "🗓 Загружаю экономический календарь..."),
          "admin_alerts": (cmd_alerts, "📡 Проверяю технические алерты..."),
          "admin_heatmap": (cmd_heatmap, "🌡 Генерирую тепловую карту..."),
          "admin_cot": (cmd_cot, "📊 Загружаю COT Report..."),
          "admin_13f": (cmd_13f, "🏦 Загружаю 13F отчёты..."),
          "admin_sentiment": (cmd_sentiment, "📊 Собираю индикаторы настроения..."),
          "admin_sectors": (cmd_sectors, "📊 Анализирую секторы..."),
          "admin_snapshot": (cmd_snapshot, "📊 Собираю market snapshot..."),
          "admin_screener": (cmd_screener, "🔍 Запускаю screener..."),
          "admin_channels": (cmd_channels, "📡 Получаю список каналов..."),
      }

      if data in handlers_map:
          handler, loading_msg = handlers_map[data]
          # Send loading message
          await query.message.reply_text(loading_msg)

          # Set admin_id in context for the handler
          context.bot_data["admin_id"] = admin_id

          # Create a fake update - we'll temporarily disable admin check
          fake_update = Update(
              update_id=update.update_id,
              message=query.message,
          )

          # Temporarily mark this context as "already verified admin" so @admin_only passes
          context.bot_data["_skip_admin_check"] = True

          try:
              await handler(fake_update, context)
          finally:
              # Clean up the flag
              context.bot_data.pop("_skip_admin_check", None)
      return

  if data == "status":
      user = query.from_user
      if not user:
          return
      stats = await storage.get_accuracy_stats(days=7)
      # Send track record to user's private chat
      await context.bot.send_message(
          chat_id=user.id,
          text=(
              "📊 <b>Трек-рекорд за 7 дней</b>\n\n"
              f"Сигналов: <b>{stats['total']}</b>\n"
              f"Точность: <b>{stats['accuracy_pct'] or 'н/д'}%</b>\n"
              f"Средний PnL: <b>{stats.get('avg_pnl', 0):+.2f}%</b>"
          ),
          parse_mode="HTML",
      )
      # Silent acknowledgment
      await query.answer()
      return
  if data.startswith("chart_"):
      ticker = data.removeprefix("chart_")
      user = query.from_user
      if not user:
          return
      try:
          from modules import charting
          image = await asyncio.to_thread(charting.build_chart, ticker)
          if image:
              # Send chart to user's private chat, not to the group
              await context.bot.send_photo(
                  chat_id=user.id,
                  photo=io.BytesIO(image),
                  caption=f"<b>{html.escape(ticker)}</b> · график TRIADA INVESTING",
                  parse_mode="HTML",
              )
              # Silent acknowledgment (no message in group)
              await query.answer()
          else:
              await query.answer("График временно недоступен", show_alert=True)
      except Exception as exc:
          logger.error("Chart callback error: %s", exc)
          await query.answer("Не удалось построить график", show_alert=True)


async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
  """Handle feedback messages from users."""
  if not update.message or not update.message.text:
      return

  text = update.message.text.strip()
  user = update.effective_user

  # Check if message starts with "ИДЕЯ" or "IDEA"
  if text.upper().startswith("ИДЕЯ") or text.upper().startswith("IDEA"):
      # Forward to admin
      admin_id = context.bot_data.get("admin_id", ADMIN_ID)
      if admin_id:
          feedback_text = (
              f"💡 <b>Новая идея от пользователя</b>\n\n"
              f"👤 От: {user.first_name} {user.last_name or ''} (@{user.username or 'без username'})\n"
              f"🆔 ID: <code>{user.id}</code>\n\n"
              f"📝 <b>Сообщение:</b>\n{html.escape(text)}"
          )
          await context.bot.send_message(
              chat_id=admin_id,
              text=feedback_text,
              parse_mode="HTML"
          )

          # Confirm to user
          await update.message.reply_text(
              "✅ <b>Спасибо за вашу идею!</b>\n\n"
              "Мы получили ваше сообщение и обязательно его рассмотрим. "
              "Лучшие идеи реализуем в ближайших обновлениях! 🚀",
              parse_mode="HTML"
          )
          logger.info(f"Feedback from user {user.id}: {text[:50]}...")


# ─── Main ─────────────────────────────────────────────────────────────────────
async def main():
  global application, scheduler

  await storage.init_db()

  threading.Thread(target=run_flask, daemon=True).start()
  logger.info("Flask dashboard started on :5000")

  is_render = bool(os.environ.get("RENDER"))
  if not is_render:
      logger.warning("Not running on Render — Telegram polling DISABLED to avoid conflict. Flask only.")
      while True:
          await asyncio.sleep(60)
      return

  application = ApplicationBuilder().token(BOT_TOKEN).build()

  application.add_handler(CommandHandler("start",    cmd_start))
  application.add_handler(CommandHandler("status",   cmd_status))
  application.add_handler(CommandHandler("test",     cmd_test))
  application.add_handler(CommandHandler("breaking", cmd_breaking))
  application.add_handler(CommandHandler("hourly",   cmd_hourly))
  application.add_handler(CommandHandler("morning",  cmd_morning))
  application.add_handler(CommandHandler("evening",  cmd_evening))
  application.add_handler(CommandHandler("weekly",   cmd_weekly))
  application.add_handler(CommandHandler("monthly",  cmd_monthly))
  application.add_handler(CommandHandler("leaders",  cmd_leaders))
  application.add_handler(CommandHandler("pulse",    cmd_pulse))
  application.add_handler(CommandHandler("earnings", cmd_earnings))
  application.add_handler(CommandHandler("calendar", cmd_calendar))
  application.add_handler(CommandHandler("alerts",   cmd_alerts))
  application.add_handler(CommandHandler("heatmap",  cmd_heatmap))
  application.add_handler(CommandHandler("cot",      cmd_cot))
  application.add_handler(CommandHandler("13f",      cmd_13f))
  application.add_handler(CommandHandler("testall",  cmd_testall))
  application.add_handler(CommandHandler("channels", cmd_channels))
  application.add_handler(CommandHandler("addchannel", cmd_addchannel))
  application.add_handler(CommandHandler("removechannel", cmd_removechannel))
  application.add_handler(CommandHandler("snapshot", cmd_snapshot))
  application.add_handler(CommandHandler("screener", cmd_screener))
  application.add_handler(CommandHandler("sentiment", cmd_sentiment))
  application.add_handler(CommandHandler("sectors", cmd_sectors))

  # User commands (available to all users)
  application.add_handler(CommandHandler("portfolio", user_commands.cmd_portfolio))
  application.add_handler(CommandHandler("add", user_commands.cmd_add))
  application.add_handler(CommandHandler("remove", user_commands.cmd_remove))
  application.add_handler(CommandHandler("analyze", user_commands.cmd_analyze))
  application.add_handler(CommandHandler("compare", user_commands.cmd_compare))
  application.add_handler(CommandHandler("backtest", user_commands.cmd_backtest))
  application.add_handler(CommandHandler("news", user_commands.cmd_news))
  application.add_handler(CommandHandler("ideas", user_commands.cmd_ideas))
  application.add_handler(CommandHandler("fundamentals", user_commands.cmd_fundamentals))
  application.add_handler(CommandHandler("peers", user_commands.cmd_peers))
  application.add_handler(CommandHandler("analysts", user_commands.cmd_analysts))
  application.add_handler(CommandHandler("alert", user_commands.cmd_alert))
  application.add_handler(CommandHandler("smartalert", user_commands.cmd_smartalert))
  application.add_handler(CommandHandler("delalert", user_commands.cmd_delalert))
  application.add_handler(CommandHandler("watch", user_commands.cmd_watch))
  application.add_handler(CommandHandler("unwatch", user_commands.cmd_unwatch))
  application.add_handler(CommandHandler("chart", user_commands.cmd_chart))
  application.add_handler(CommandHandler("stats", user_commands.cmd_stats))

  application.add_handler(CallbackQueryHandler(handle_callback))

  # Message handler for feedback (must be last, catches all text messages)
  from telegram.ext import MessageHandler, filters
  application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_feedback))

  admin_id = str(ADMIN_ID) if ADMIN_ID else ""
  application.bot_data["admin_id"] = admin_id

  async with application:
      await application.initialize()
      await application.start()

      # Setup bot menu commands (different for admin and users)
      await bot_commands.setup_bot_commands(application.bot, admin_id)

      topic_ids = await forum_topics.ensure_topics_exist(application.bot, GROUP_CHAT_ID)
      forum_topics.set_topic_ids(topic_ids)
      logger.info("Forum topics initialized: %s", topic_ids)

      scheduler = build_scheduler(application.bot, admin_id)
      scheduler.start()
      logger.info("Scheduler started with all jobs (misfire_grace_time=600s)")

      if admin_id:
          sqlite_ok = False
          try:
              stats = await storage.get_today_stats()
              sqlite_ok = True
              sqlite_status = "✅ SQLite — OK"
          except Exception as e:
              sqlite_status = f"❌ SQLite — ОШИБКА: {e}"

          redis_ok, redis_error = await dedup.check_redis_connection()
          if redis_ok:
              redis_status = "✅ Upstash Redis — OK"
          elif not dedup.USE_REDIS:
              redis_status = "⚠️ Upstash Redis — не настроен (fallback SQLite)"
          else:
              redis_status = f"❌ Upstash Redis — ошибка: {redis_error}"

          overall = "✅ Бот запущен" if (sqlite_ok and redis_ok) else "⚠️ Бот запущен с предупреждениями"
          msg = (
              f"🤖 <b>TRIADA INVESTING Bot — старт</b>\n\n"
              f"{overall}\n\n"
              f"<b>Базы данных:</b>\n"
              f"{sqlite_status}\n"
              f"{redis_status}\n\n"
              f"<b>Исправления в этой версии:</b>\n"
              f"• Планировщик: misfire_grace_time=600с (задачи больше не пропускаются)\n"
              f"• Все сетевые вызовы вынесены в asyncio.to_thread\n"
              f"• Пульс рынка: обход кэша yfinance\n"
              f"• Finviz: детект заглушки 'Chart not available' по размеру\n"
              f"• Трек-рекорд: публикует результат проверки в канал\n"
              f"• Технические алерты RSI/SMA: автоматически каждый час + /alerts\n"
              f"• Фото-заглушки: используются файлы из assets/stubs/\n\n"
              f"<b>Новые функции:</b>\n"
              f"• COT Report (CFTC, пятница 23:00 МСК) — /cot\n"
              f"• 13F Filings (SEC EDGAR, пн 10:00 МСК) — /13f\n"
              f"• Форум-темы: {len(topic_ids)}/{len(forum_topics.TOPIC_NAMES)} ID загружено\n"
              f"• Telegram-мониторинг: каждые 5 минут (если TG_* настроены)"
          )
          await notify_admin(application.bot, admin_id, msg)
          logger.info(f"Startup diagnostic sent. SQLite={sqlite_ok}, Redis={redis_ok}")

      polling_owner = f"{os.getpid()}-{uuid.uuid4().hex}"
      polling_lock_name = "telegram_polling"
      polling_lock_acquired = False
      polling_renew_task = None

      if dedup.USE_REDIS:
          # Render can overlap old/new processes during a deploy. Wait for
          # the old process to release the lock instead of causing Telegram's
          # 409 Conflict by starting a second getUpdates request.
          for _ in range(60):
              polling_lock_acquired = await dedup.acquire_lock(
                  polling_lock_name, polling_owner, ttl=120
              )
              if polling_lock_acquired:
                  break
              logger.warning("Another TRIADA process owns Telegram polling; waiting 2s")
              await asyncio.sleep(2)

          if not polling_lock_acquired:
              raise RuntimeError(
                  "Telegram polling lock is busy for 120s; refusing to start a second getUpdates loop"
              )

          async def renew_polling_lock():
              while True:
                  await asyncio.sleep(30)
                  if not await dedup.renew_lock(
                      polling_lock_name, polling_owner, ttl=120
                  ):
                      logger.error("Telegram polling lock was lost; stopping this process")
                      return

          polling_renew_task = asyncio.create_task(renew_polling_lock())
      else:
          logger.warning(
              "Redis is unavailable: Telegram polling cannot be protected from "
              "a second Render process"
          )

      try:
          if application.updater:
              await application.updater.start_polling(drop_pending_updates=True)
          logger.info("Bot polling started — TRIADA INVESTING is live")
          while True:
              await asyncio.sleep(1)
      finally:
          if polling_renew_task:
              polling_renew_task.cancel()
          if polling_lock_acquired:
              await dedup.release_lock(polling_lock_name, polling_owner)


if __name__ == "__main__":
  try:
      asyncio.run(main())
  except (KeyboardInterrupt, SystemExit):
      logger.info("Bot stopped")
  except Exception as e:
      logger.critical(f"Fatal: {e}", exc_info=True)

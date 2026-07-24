import asyncio
import logging
import os
import threading
from datetime import datetime

import pytz
from flask import Flask, render_template_string
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from config.config import BOT_TOKEN, ADMIN_USERNAME, ADMIN_ID, CHANNEL_ID
from modules import pipeline, storage, dedup
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
<p>✅ AI: Groq llama-3.3-70b-versatile</p>
<p>✅ AI-критик: Google Gemini (только high-impact BREAKING)</p>
<p>✅ Графики: Finviz → yfinance+matplotlib (fallback)</p>
<p>✅ Фото: стабы для плановых постов / RSS→Wikimedia→Google CSE→Pexels для BREAKING</p>
<p>✅ Антидубль: Upstash Redis → SQLite (fallback), 2 уровня проверки</p>
<p>✅ Трек-рекорд: сверка рекомендаций через 24ч (yfinance)</p>
<p>✅ Лидеры: мировой рынок (S&P 500 / NASDAQ), макс. 1 рос. компания</p>
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
@admin_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  text = (
      "🤖 <b>TRIADA INVESTING Bot</b>\n\n"
      "<b>Ручные команды:</b>\n"
      "/breaking — срочные новости прямо сейчас\n"
      "/hourly — часовой дайджест прямо сейчас\n"
      "/morning — утренний обзор прямо сейчас\n"
      "/evening — вечерний обзор прямо сейчас\n"
      "/weekly — недельный итог прямо сейчас\n"
      "/monthly — месячный итог прямо сейчас\n"
      "/leaders — лидеры роста/падения мирового рынка\n"
      "/pulse — обновить пульс рынка прямо сейчас\n"
      "/earnings — дайджест отчётностей компаний\n"
      "/calendar — экономический календарь\n"
      "/alerts — технические алерты (RSI / SMA)\n"
      "/heatmap — тепловая карта секторов\n\n"
      "<b>Служебные:</b>\n"
      "/status — статус бота и статистика\n"
      "/test — быстрый тест (breaking → hourly)\n\n"
      "Бот публикует автоматически по расписанию МСК."
  )
  await update.message.reply_text(text, parse_mode="HTML")


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
  next_str = "\n".join(next_jobs[:6]) if next_jobs else "нет данных"

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
              "Проверьте GROQ_API_KEY и подключение к RSS."
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
          else "ℹ️ Нет событий в календаре."
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

  admin_id = str(ADMIN_ID) if ADMIN_ID else ""
  application.bot_data["admin_id"] = admin_id

  scheduler = build_scheduler(application.bot, admin_id)
  scheduler.start()
  logger.info("Scheduler started with all jobs")

  async with application:
      await application.initialize()
      await application.start()

      if admin_id:
          sqlite_ok = False
          try:
              stats = await storage.get_today_stats()
              sqlite_ok = True
              sqlite_status = "✅ SQLite — OK (данные сохраняются локально)"
          except Exception as e:
              sqlite_status = f"❌ SQLite — ОШИБКА: {e}"

          redis_ok, redis_error = await dedup.check_redis_connection()
          if redis_ok:
              redis_status = "✅ Upstash Redis — OK (антидубль персистентный)"
          elif not dedup.USE_REDIS:
              redis_status = "⚠️ Upstash Redis — не настроен (антидубль через SQLite, сбрасывается при рестарте)"
          else:
              redis_status = f"❌ Upstash Redis — ошибка: {redis_error}"

          overall = "✅ Бот запущен и работает" if (sqlite_ok and redis_ok) else "⚠️ Бот запущен с предупреждениями"
          msg = (
              f"🤖 <b>TRIADA INVESTING Bot — старт</b>\n\n"
              f"{overall}\n\n"
              f"<b>Базы данных:</b>\n"
              f"{sqlite_status}\n"
              f"{redis_status}\n\n"
              f"<b>Активные модули:</b>\n"
              f"• Пульс рынка (каждые 15 мин)\n"
              f"• Экономический календарь FRED\n"
              f"• Технические алерты RSI/SMA\n"
              f"• Дайджест отчётностей компаний\n"
              f"• Тепловая карта секторов\n"
              f"• Лидеры: мировой рынок (S&P 500 / NASDAQ)"
          )
          await notify_admin(application.bot, admin_id, msg)
          logger.info(f"Startup diagnostic sent to admin. SQLite={sqlite_ok}, Redis={redis_ok}")

      if application.updater:
          await application.updater.start_polling(drop_pending_updates=True)
      logger.info("Bot polling started — TRIADA INVESTING is live")
      while True:
          await asyncio.sleep(1)


if __name__ == "__main__":
  try:
      asyncio.run(main())
  except (KeyboardInterrupt, SystemExit):
      logger.info("Bot stopped")
  except Exception as e:
      logger.critical(f"Fatal: {e}", exc_info=True)

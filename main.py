import asyncio
import html
import logging
import os
import threading
import uuid
from datetime import datetime

import pytz
from flask import Flask, render_template_string
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from config.config import BOT_TOKEN, ADMIN_USERNAME, ADMIN_ID, CHANNEL_ID, GROUP_CHAT_ID
from modules import pipeline, storage, dedup, forum_topics, telegram_monitor
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
<p>✅ AI-критик: Groq gemma2-9b-it (только high-impact BREAKING)</p>
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
      "/heatmap — тепловая карта секторов\n"
      "/cot — позиции крупных игроков (COT/CFTC)\n"
      "/13f — отчёты крупных фондов (13F/SEC)\n\n"
      "<b>Мониторинг Telegram-каналов:</b>\n"
      "/channels — список каналов\n"
      "/addchannel @channel — добавить канал\n"
      "/removechannel @channel — удалить канал\n\n"
      "<b>Служебные:</b>\n"
      "/status — статус бота и статистика\n"
      "/test — быстрый тест (breaking → hourly)\n\n"
      "Бот публикует автоматически по расписанию МСК."
  )
  await update.message.reply_text(text, parse_mode="HTML")


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

  admin_id = str(ADMIN_ID) if ADMIN_ID else ""
  application.bot_data["admin_id"] = admin_id

  async with application:
      await application.initialize()
      await application.start()

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

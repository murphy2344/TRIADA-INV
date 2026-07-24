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
  <p>✅ Фото: статья → Wikimedia → Google CSE → Pexels/Pixabay</p>
  <p>✅ Антидубль: Upstash Redis → SQLite (fallback), 2 уровня проверки</p>
  <p>✅ Трек-рекорд: сверка рекомендаций через 24ч (yfinance)</p>
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
        "🤖 <b>TRIADA INVESTING Bot запущен</b>\n\n"
        "Доступные команды:\n"
        "/start — этот список\n"
        "/status — статус бота и статистика\n"
        "/test — тестовая публикация в канал прямо сейчас\n"
        "/leaders — лидеры роста/падения MOEX прямо сейчас\n"
        "/stop — не предусмотрен (бот работает автономно 24/7)\n\n"
        "Бот публикует новости по расписанию МСК автоматически."
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
    await update.message.reply_text("🧪 Запускаю тестовую публикацию, подождите...")
    admin_id = str(update.effective_chat.id)
    try:
        posted = await pipeline.run_breaking(context.bot, admin_id)
        if posted == 0:
            posted = await pipeline.run_hourly(context.bot, admin_id)
        if posted > 0:
            await update.message.reply_text(f"✅ Тест выполнен, опубликовано постов: {posted}")
        else:
            await update.message.reply_text(
                "❌ Тест не удался: нет новых новостей или ошибка AI.\n"
                "Проверьте GROQ_API_KEY и подключение к RSS."
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Тест не удался: {e}")


@admin_only
async def cmd_leaders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Собираю лидеров роста/падения MOEX, подождите...")
    admin_id = str(update.effective_chat.id)
    try:
        posted = await pipeline.run_leaders(context.bot, admin_id)
        if posted > 0:
            await update.message.reply_text("✅ Пост с лидерами MOEX опубликован.")
        else:
            await update.message.reply_text(
                "❌ Не удалось опубликовать: нет данных с MOEX ISS "
                "(возможно, выходной день на бирже, или сервис недоступен)."
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


# ─── Main ─────────────────────────────────────────────────────────────────────
async def main():
    global application, scheduler

    await storage.init_db()

    threading.Thread(target=run_flask, daemon=True).start()
    logger.info("Flask dashboard started on :5000")

    # On Render: RENDER env var is set automatically → run full bot
    # On Replit / local: only Flask dashboard, NO Telegram polling (avoids conflict)
    is_render = bool(os.environ.get("RENDER"))
    if not is_render:
        logger.warning("Not running on Render — Telegram polling DISABLED to avoid conflict. Flask only.")
        while True:
            await asyncio.sleep(60)
        return

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("test", cmd_test))
    application.add_handler(CommandHandler("leaders", cmd_leaders))

    admin_id = str(ADMIN_ID) if ADMIN_ID else ""
    application.bot_data["admin_id"] = admin_id

    scheduler = build_scheduler(application.bot, admin_id)
    scheduler.start()
    logger.info("Scheduler started with all jobs")

    # ── Диагностика баз данных при старте ────────────────────────────────────
    # Проверяем SQLite и Upstash Redis, отправляем отчёт в личку админу
    async with application:
        await application.initialize()
        await application.start()

        if admin_id:
            # 1. SQLite
            sqlite_ok = False
            try:
                stats = await storage.get_today_stats()
                sqlite_ok = True
                sqlite_status = "✅ SQLite — OK (данные сохраняются локально)"
            except Exception as e:
                sqlite_status = f"❌ SQLite — ОШИБКА: {e}"

            # 2. Upstash Redis
            redis_ok, redis_error = await dedup.check_redis_connection()
            if redis_ok:
                redis_status = "✅ Upstash Redis — OK (антидубль персистентный)"
            elif not dedup.USE_REDIS:
                redis_status = "⚠️ Upstash Redis — не настроен (антидубль через SQLite, сбрасывается при рестарте)"
            else:
                redis_status = f"❌ Upstash Redis — ошибка: {redis_error}"

            # 3. Итоговое сообщение
            overall = "✅ Бот запущен и работает" if (sqlite_ok and redis_ok) else "⚠️ Бот запущен с предупреждениями"
            msg = (
                f"🤖 <b>TRIADA INVESTING Bot — старт</b>\n\n"
                f"{overall}\n\n"
                f"<b>Базы данных:</b>\n"
                f"{sqlite_status}\n"
                f"{redis_status}\n\n"
                f"<b>Новые модули активны:</b>\n"
                f"• Пульс рынка (каждые 15 мин)\n"
                f"• Экономический календарь FRED\n"
                f"• Технические алерты RSI/SMA\n"
                f"• Дайджест отчётностей компаний\n"
                f"• Тепловая карта секторов"
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

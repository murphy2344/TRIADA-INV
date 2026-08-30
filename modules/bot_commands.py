"""Setup bot menu commands with different scopes for admin and regular users."""
import logging
from telegram import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

logger = logging.getLogger(__name__)


async def setup_bot_commands(bot, admin_id: str):
    """Set up bot menu commands - separate menus for admin and regular users."""
    try:
        logger.info(f"Setting up bot commands. Admin ID: {admin_id}")

        # Commands for regular users
        user_commands = [
            BotCommand("start", "Начать работу с ботом"),
            BotCommand("portfolio", "Показать портфель"),
            BotCommand("add", "Добавить позицию (TICKER кол-во цена)"),
            BotCommand("remove", "Удалить позицию"),
            BotCommand("alert", "Установить ценовой алерт"),
            BotCommand("delalert", "Удалить алерт"),
            BotCommand("watch", "Показать watchlist"),
            BotCommand("unwatch", "Удалить из watchlist"),
            BotCommand("chart", "Получить график (TICKER)"),
            BotCommand("stats", "Статистика по тикеру"),
        ]

        # Commands for admin (personal + admin management)
        admin_commands = [
            BotCommand("start", "Панель управления ботом"),
            BotCommand("portfolio", "Показать портфель"),
            BotCommand("watch", "Watchlist тикеров"),
            BotCommand("alert", "Ценовые алерты"),
            BotCommand("chart", "График (TICKER)"),
            BotCommand("stats", "Статистика по тикеру"),
            BotCommand("status", "Статус бота"),
            BotCommand("test", "Тест (breaking → hourly)"),
            BotCommand("breaking", "Срочные новости"),
            BotCommand("hourly", "Часовой дайджест"),
            BotCommand("morning", "Утренний обзор"),
            BotCommand("evening", "Вечерний обзор"),
            BotCommand("weekly", "Недельный итог"),
            BotCommand("monthly", "Месячный итог"),
            BotCommand("leaders", "Лидеры рынка"),
            BotCommand("pulse", "Обновить пульс рынка"),
            BotCommand("earnings", "Дайджест отчётностей"),
            BotCommand("calendar", "Экономический календарь"),
            BotCommand("alerts", "Технические алерты"),
            BotCommand("heatmap", "Тепловая карта секторов"),
            BotCommand("cot", "COT Report (CFTC)"),
            BotCommand("13f", "13F Filings (SEC)"),
            BotCommand("channels", "Список каналов мониторинга"),
            BotCommand("testall", "Полная диагностика"),
        ]

        # Set default commands for all users
        await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
        logger.info(f"User commands set successfully: {len(user_commands)} commands")

        # Set admin-specific commands if admin_id is provided
        if admin_id:
            await bot.set_my_commands(
                admin_commands,
                scope=BotCommandScopeChat(chat_id=int(admin_id))
            )
            logger.info(f"Admin commands set successfully for chat_id={admin_id}: {len(admin_commands)} commands")

    except Exception as e:
        logger.error(f"Error setting bot commands: {e}")

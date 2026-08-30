"""Setup bot menu commands with different scopes for admin and regular users."""
import logging
from telegram import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

logger = logging.getLogger(__name__)


async def setup_bot_commands(bot, admin_id: str):
    """Set up bot menu commands - only user commands in quick access menu."""
    try:
        logger.info(f"Setting up bot commands. Admin ID: {admin_id}")

        # Commands for ALL users (visible in quick access menu)
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

        # Set commands for everyone (including admin) - no separate admin menu
        await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
        logger.info(f"User commands set successfully: {len(user_commands)} commands")

    except Exception as e:
        logger.error(f"Error setting bot commands: {e}")

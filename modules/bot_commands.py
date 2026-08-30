"""Setup bot menu commands with different scopes for admin and regular users."""
import logging
from telegram import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

logger = logging.getLogger(__name__)


async def setup_bot_commands(bot, admin_id: str):
    """Set up bot menu commands with different visibility for admin and users."""
    try:
        # Commands for regular users (visible to everyone)
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

        # Set default commands for all users
        await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
        logger.info("User commands set successfully")

        # Admin commands (visible only to admin)
        if admin_id:
            admin_commands = [
                BotCommand("start", "Начать работу с ботом"),
                # Admin controls
                BotCommand("status", "Статус бота"),
                BotCommand("test", "Быстрый тест"),
                BotCommand("testall", "Полная диагностика"),
                # Manual publishing
                BotCommand("breaking", "Срочные новости"),
                BotCommand("hourly", "Часовой дайджест"),
                BotCommand("morning", "Утренний обзор"),
                BotCommand("evening", "Вечерний обзор"),
                BotCommand("weekly", "Недельный итог"),
                BotCommand("monthly", "Месячный итог"),
                BotCommand("leaders", "Лидеры роста/падения"),
                BotCommand("pulse", "Обновить пульс рынка"),
                BotCommand("earnings", "Дайджест отчётностей"),
                BotCommand("calendar", "Экономический календарь"),
                BotCommand("alerts", "Технические алерты"),
                BotCommand("heatmap", "Тепловая карта секторов"),
                BotCommand("cot", "Позиции крупных игроков"),
                BotCommand("13f", "Отчёты крупных фондов"),
                # Channel monitoring
                BotCommand("channels", "Список каналов"),
                BotCommand("addchannel", "Добавить канал"),
                BotCommand("removechannel", "Удалить канал"),
                # User commands (also visible to admin)
                BotCommand("portfolio", "Показать портфель"),
                BotCommand("add", "Добавить позицию"),
                BotCommand("alert", "Установить алерт"),
                BotCommand("watch", "Показать watchlist"),
                BotCommand("chart", "Получить график"),
                BotCommand("stats", "Статистика по тикеру"),
            ]

            try:
                await bot.set_my_commands(
                    admin_commands,
                    scope=BotCommandScopeChat(chat_id=int(admin_id))
                )
                logger.info(f"Admin commands set for user {admin_id}")
            except Exception as e:
                logger.error(f"Failed to set admin commands: {e}")

    except Exception as e:
        logger.error(f"Error setting bot commands: {e}")

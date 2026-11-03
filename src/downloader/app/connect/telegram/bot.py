import asyncio
import fcntl
import logging
from pathlib import Path
import sys
from typing import IO

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from downloader.app.config.settings import get_settings
from downloader.app.connect.telegram.handlers import (
    booru,
    inline,
    link,
    search,
    settings,
    torrent,
    upload,
    vault,
)
from downloader.app.connect.telegram.middlewares.auth import WhitelistAuthMiddleware
from downloader.app.connect.telegram.middlewares.debounce import CallbackDebounceMiddleware

logger = logging.getLogger("downloader.telegram")

_dp_instance: Dispatcher | None = None
_LOCK_FILE_PATH = Path("/tmp/downloader_telegram_bot.lock")


def get_telegram_dispatcher() -> Dispatcher:
    """Створює або повертає синглтон Dispatcher із підключеними роутерами та middlewares."""
    global _dp_instance
    if _dp_instance is not None:
        return _dp_instance

    dp = Dispatcher()

    auth_mw = WhitelistAuthMiddleware()
    dp.message.middleware(auth_mw)
    dp.callback_query.middleware(auth_mw)
    dp.callback_query.middleware(CallbackDebounceMiddleware())

    dp.include_router(settings.router)
    dp.include_router(inline.router)
    dp.include_router(search.router)
    dp.include_router(vault.router)
    dp.include_router(booru.router)
    dp.include_router(torrent.router)
    dp.include_router(upload.router)
    dp.include_router(link.router)

    _dp_instance = dp
    return dp


async def setup_bot_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Головне меню та огляд функцій"),
        BotCommand(command="menu", description="Швидке інтерактивне меню з кнопками"),
        BotCommand(command="vault", description="Сховище: /vault [тег] [кількість в чат]"),
        BotCommand(command="booru", description="Yande.re Booru: /booru [тег] [к-сть]"),
        BotCommand(command="settings", description="Якість відео, формат та макс. сторона фото"),
        BotCommand(command="tasks", description="Статус активних завантажень та черга"),
        BotCommand(command="id", description="Дізнатися свій Telegram ID"),
        BotCommand(command="help", description="Довідка та інструкція"),
    ]
    try:
        await bot.set_my_commands(commands)
    except Exception as exc:
        logger.warning("Не вдалося оновити меню команд бота: %s", exc)


def _acquire_bot_lock() -> IO[str] | None:
    """Гарантує, що лише один процес одночасно робить getUpdates для уникнення TelegramConflictError."""
    try:
        fh = open(_LOCK_FILE_PATH, "w", encoding="utf-8")
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fh
    except OSError:
        return None


def _release_bot_lock(fh: IO[str] | None) -> None:
    if not fh:
        return
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()
    except Exception:
        pass


async def run_bot(handle_signals: bool = True) -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            stream=sys.stdout,
        )

    app_settings = get_settings()
    token = app_settings.TELEGRAM_BOT_TOKEN.get_secret_value().strip()
    if not token or token == "your_bot_token_here":
        logger.warning("TELEGRAM_BOT_TOKEN не заданий у .env — Telegram-бот не запущено.")
        return

    lock_fh = _acquire_bot_lock()
    if lock_fh is None:
        logger.info(
            "ℹ️ Telegram-бот вже активно працює в іншому процесі (виявлено lock-файл %s). "
            "Пропускаємо повторний запуск polling, щоб уникнути TelegramConflictError.",
            _LOCK_FILE_PATH,
        )
        return

    bot = Bot(token=token)
    dp = get_telegram_dispatcher()

    try:
        await setup_bot_commands(bot)
        me = await bot.get_me()
        logger.info("🚀 Telegram-бот успішно запущений як @%s (ID: %s)", me.username, me.id)

        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, handle_signals=handle_signals)
    except asyncio.CancelledError:
        logger.info("🛑 Фоновий процес Telegram-бота зупинено.")
    except Exception as exc:
        logger.error("Помилка роботи Telegram-бота: %s", exc)
    finally:
        try:
            await bot.session.close()
        except Exception:
            pass
        _release_bot_lock(lock_fh)


def main() -> None:
    asyncio.run(run_bot(handle_signals=True))


if __name__ == "__main__":
    main()

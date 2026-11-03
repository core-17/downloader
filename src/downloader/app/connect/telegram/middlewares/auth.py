from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from downloader.app.config.settings import get_settings


class WhitelistAuthMiddleware(BaseMiddleware):
    """
    Перевіряє доступ користувача за списком TELEGRAM_ALLOWED_USERS.
    Якщо список у .env порожній або не налаштований — доступ відкритий для всіх.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        allowed = self.settings.TELEGRAM_ALLOWED_USERS
        if not allowed:
            return await handler(event, data)

        user = data.get("event_from_user")
        if user and user.id in allowed:
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer(
                f"⛔ Доступ обмежено.\nВаш Telegram ID: <code>{user.id if user else 'unknown'}</code>",
                parse_mode="HTML",
            )
        elif isinstance(event, CallbackQuery):
            await event.answer("⛔ Немає доступу", show_alert=True)
        return None


from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from downloader.app.config.settings import get_settings
from downloader.app.core.accounts import account_manager


class WhitelistAuthMiddleware(BaseMiddleware):
    """
    Перевіряє доступ користувача за списком TELEGRAM_ALLOWED_USERS або прив'язаними акаунтами у accounts.json.
    Також автоматично визначає та вкладає в data['account'] профіль поточного користувача.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        allowed = list(self.settings.TELEGRAM_ALLOWED_USERS or [])

        # Перевіряємо всі прив'язані до профілів Telegram ID
        for acc in account_manager.list_accounts():
            for tid in acc.bots.telegram_user_ids:
                if tid not in allowed:
                    allowed.append(tid)

        if user:
            # Зв'язуємо подію з відповідним акаунтом користувача
            acc = account_manager.get_account_by_telegram_id(user.id)
            data["account"] = acc

        if not allowed:
            return await handler(event, data)

        if user and user.id in allowed:
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer(
                f"⛔ Доступ обмежено.\nВаш Telegram ID: <code>{user.id if user else 'unknown'}</code>\n"
                f"💡 Зверніться до адміністратора або прив'яжіть цей ID до свого профілю у Веб-інтерфейсі.",
                parse_mode="HTML",
            )
        elif isinstance(event, CallbackQuery):
            await event.answer("⛔ Немає доступу. Прив'яжіть акаунт у Веб-інтерфейсі.", show_alert=True)
        return None


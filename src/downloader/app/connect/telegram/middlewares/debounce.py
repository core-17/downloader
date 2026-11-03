import time
from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject


class CallbackDebounceMiddleware(BaseMiddleware):
    """Захист від подвійних кліків по inline-кнопках."""

    def __init__(self, cooldown_sec: float = 0.4) -> None:
        self.cooldown_sec = cooldown_sec
        self._last_click: dict[tuple[int, str], float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, CallbackQuery) and event.from_user and event.data:
            key = (event.from_user.id, event.data)
            now = time.monotonic()
            last = self._last_click.get(key, 0.0)
            if now - last < self.cooldown_sec:
                await event.answer()
                return None
            self._last_click[key] = now
        return await handler(event, data)


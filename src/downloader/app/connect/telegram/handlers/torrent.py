from aiogram import F, Router
from aiogram.types import Message

router = Router(name="torrent_router")


@router.message(F.text.startswith("magnet:?xt="))
async def handle_magnet(message: Message) -> None:
    await message.answer(
        "🧲 <b>Magnet-посилання розпізнано.</b>\n"
        "Модуль торент-клієнта знаходиться в черзі на наступний етап реалізації.",
        parse_mode="HTML",
    )


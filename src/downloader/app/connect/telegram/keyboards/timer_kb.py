from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_timer_keyboard(task_id: str, seconds: int = 5) -> InlineKeyboardMarkup:
    """Клавіатура 'Правила 5 секунд' при отриманні посилання."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🚀 За дефолтом ({seconds}с)",
                    callback_data=f"dl_now:{task_id}",
                ),
                InlineKeyboardButton(
                    text="⚙️ Налаштувати",
                    callback_data=f"dl_cfg:{task_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Скасувати",
                    callback_data=f"dl_cancel:{task_id}",
                )
            ],
        ]
    )


def build_task_quality_keyboard(task_id: str) -> InlineKeyboardMarkup:
    """Клавіатура вибору профілю якості/формату для конкретного посилання."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎬 1080p", callback_data=f"dl_q:{task_id}:1080"),
                InlineKeyboardButton(text="🎬 720p", callback_data=f"dl_q:{task_id}:720"),
                InlineKeyboardButton(text="🎬 480p", callback_data=f"dl_q:{task_id}:480"),
            ],
            [
                InlineKeyboardButton(text="🔥 Max (4K)", callback_data=f"dl_q:{task_id}:2160"),
                InlineKeyboardButton(text="🎵 Тільки аудіо (MP3)", callback_data=f"dl_q:{task_id}:audio"),
            ],
            [
                InlineKeyboardButton(text="❌ Скасувати", callback_data=f"dl_cancel:{task_id}"),
            ],
        ]
    )


from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_user_settings_keyboard(
    current_quality: str,
    instant_mode: bool,
    image_format: str = "original",
    image_max_side: int | None = None,
) -> InlineKeyboardMarkup:
    """Клавіатура глобальних налаштувань користувача (/settings)."""
    qualities = ["480p", "720p", "1080p", "4k", "best"]
    q_buttons = [
        InlineKeyboardButton(
            text=f"{'✅ ' if current_quality.lower() == q else ''}{q.upper()}",
            callback_data=f"set_q:{q}",
        )
        for q in qualities
    ]

    img_formats = ["original", "webp", "jpg", "png"]
    img_buttons = [
        InlineKeyboardButton(
            text=f"{'✅ ' if image_format.lower() == fmt else ''}{fmt.upper()}",
            callback_data=f"set_img_fmt:{fmt}",
        )
        for fmt in img_formats
    ]

    # Кнопки обмеження розміру по більшій стороні (збереження пропорцій)
    sides = [(None, "ORIG"), (1080, "1080p"), (1920, "1920p"), (2560, "2K")]
    side_buttons = [
        InlineKeyboardButton(
            text=f"{'📐 ' if image_max_side == s else ''}{lbl}",
            callback_data=f"set_side:{s if s is not None else 'orig'}",
        )
        for s, lbl in sides
    ]

    mode_text = (
        "⚡ Режим: Миттєво (без 5с таймера)"
        if instant_mode
        else "⏱️ Режим: Таймер 5 секунд (меню вибору)"
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Якість відео:", callback_data="noop")],
            q_buttons,
            [InlineKeyboardButton(text="🖼️ Формат зображень:", callback_data="noop")],
            img_buttons,
            [InlineKeyboardButton(text="📐 Макс. сторона фото:", callback_data="noop")],
            side_buttons,
            [
                InlineKeyboardButton(
                    text=mode_text,
                    callback_data="set_mode:toggle",
                )
            ],
        ]
    )

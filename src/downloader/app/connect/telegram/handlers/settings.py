from dataclasses import dataclass
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from downloader.app.config.constants import QUALITY_HEIGHT_MAP
from downloader.app.config.settings import get_settings
from downloader.app.connect.telegram.keyboards.settings_kb import build_user_settings_keyboard

router = Router(name="settings_router")


@dataclass
class UserPrefs:
    quality: str = "1080p"
    instant_mode: bool = False
    image_format: str = "original"
    image_max_side: int | None = None

    @property
    def max_height(self) -> int:
        if self.quality.lower() in ("best", "original", "max"):
            return 0
        return QUALITY_HEIGHT_MAP.get(self.quality.lower(), 1080)


_user_prefs: dict[int, UserPrefs] = {}


def get_user_prefs(user_id: int) -> UserPrefs:
    if user_id not in _user_prefs:
        settings = get_settings()
        _user_prefs[user_id] = UserPrefs(
            quality=settings.DEFAULT_VIDEO_QUALITY.lower(),
            instant_mode=False,
            image_format="original",
            image_max_side=None,
        )
    return _user_prefs[user_id]


def _render_settings_text(prefs: UserPrefs) -> str:
    side_str = f"{prefs.image_max_side} px" if prefs.image_max_side else "Без обмежень (оригінал)"
    return (
        "⚙️ <b>Налаштування профілю завантаження</b>\n\n"
        f"• 🎬 Якість відео: <b>{prefs.quality.upper()}</b>\n"
        f"• 🖼️ Формат зображень: <b>{prefs.image_format.upper()}</b>\n"
        f"• 📐 Макс. сторона фото: <b>{side_str}</b>\n"
        f"• ⏱️ Режим старту: <b>{'⚡ Миттєво' if prefs.instant_mode else '⏱️ Таймер 5 секунд'}</b>"
    )


def build_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Головне інтерактивне меню для швидкого доступу до функцій."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📁 Моє Сховище (файли)", callback_data="menu:vault"),
                InlineKeyboardButton(text="🌸 Yande.re Booru", callback_data="menu:booru"),
            ],
            [
                InlineKeyboardButton(text="⚙️ Налаштування якості/формату", callback_data="menu:settings"),
                InlineKeyboardButton(text="📋 Активні задачі /tasks", callback_data="menu:tasks"),
            ],
            [
                InlineKeyboardButton(text="❓ Довідка та приклади", callback_data="menu:help"),
            ]
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "👋 <b>Universal Media Downloader & Vault Bot</b>\n\n"
        "Оберіть дію в меню або надішліть будь-яке посилання/файл (з <code>#тегами</code> чи альбомом):\n\n"
        "• 🎬 <b>Відео:</b> YouTube, TikTok, Instagram, X (Twitter), Reddit, Pinterest\n"
        "• 🖼️ <b>Фото:</b> оригінали найвищої якості (Pinterest, Twitter, сайти)\n"
        "• 🌸 <b>Yande.re Booru:</b> <code>/booru [тег] [к-сть]</code>\n"
        "• 📁 <b>Сховище:</b> <code>/vault [тег] [к-сть]</code> (з масовою відправкою в чат)\n"
        "• ⚙️ <b>Налаштування:</b> конвертація фото (WebP/JPG/PNG), якість 4K/1080p, розмір сторін",
        reply_markup=build_main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer(
        "📱 <b>Головне інтерактивне меню бота:</b>",
        reply_markup=build_main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("menu:"))
async def cb_main_menu(callback: CallbackQuery) -> None:
    if not callback.data or not callback.message:
        return
    action = callback.data.split(":", 1)[1]
    uid = callback.from_user.id if callback.from_user else 0

    if action == "settings":
        prefs = get_user_prefs(uid)
        await callback.message.edit_text(
            _render_settings_text(prefs),
            reply_markup=build_user_settings_keyboard(
                prefs.quality, prefs.instant_mode, prefs.image_format, prefs.image_max_side
            ),
            parse_mode="HTML",
        )
    elif action == "vault":
        await callback.answer()
        # Імітуємо команду /vault
        from downloader.app.connect.telegram.handlers.vault import cmd_vault
        await cmd_vault(callback.message)
    elif action == "booru":
        await callback.answer()
        await callback.message.reply(
            "🌸 <b>Yande.re Booru:</b>\n\n"
            "Щоб завантажити або надіслати ілюстрації за тегом, напишіть:\n"
            "• <code>/booru landscape 5</code> — 5 ілюстрацій з пейзажами\n"
            "• <code>/booru order:score sky 10</code> — 10 найкращих з небом\n"
            "• Або вкажіть тег у будь-якому повідомленні: <code>booru:genshin_impact</code>",
            parse_mode="HTML",
        )
    elif action == "tasks":
        await callback.answer()
        from downloader.app.connect.telegram.handlers.search import cmd_tasks
        await cmd_tasks(callback.message)
    elif action == "help":
        await callback.answer()
        await cmd_help(callback.message)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "📖 <b>Довідка по командах бота:</b>\n\n"
        "1️⃣ <b>Завантаження:</b> просто надішліть посилання на пост чи відео. Діє правило 5 секунд (можна налаштувати якість або почати миттєво).\n"
        "2️⃣ <b>Yande.re Booru:</b> команда <code>/booru [тег] [к-сть]</code> знайде і надішле галерею з інлайн-кнопками дій.\n"
        "3️⃣ <b>Сховище:</b> команда <code>/vault [пошук]</code> покаже останні файли сховища з прямими посиланнями.\n"
        "4️⃣ <b>Налаштування:</b> у меню /settings можна обрати якість відео, формат фото (WebP/JPG/PNG) та обмеження роздільної здатності.",
        parse_mode="HTML",
    )


@router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    await message.answer(
        f"🆔 Ваш Telegram ID: <code>{uid}</code>",
        parse_mode="HTML",
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    prefs = get_user_prefs(uid)
    await message.answer(
        _render_settings_text(prefs),
        reply_markup=build_user_settings_keyboard(
            prefs.quality, prefs.instant_mode, prefs.image_format, prefs.image_max_side
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("set_q:"))
async def cb_set_quality(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.data:
        return
    new_q = callback.data.split(":", 1)[1].lower()
    prefs = get_user_prefs(callback.from_user.id)
    if prefs.quality == new_q:
        await callback.answer(f"Якість вже встановлена на {new_q.upper()}")
        return
    prefs.quality = new_q
    if callback.message:
        try:
            await callback.message.edit_text(
                _render_settings_text(prefs),
                reply_markup=build_user_settings_keyboard(
                    prefs.quality, prefs.instant_mode, prefs.image_format, prefs.image_max_side
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass
    await callback.answer(f"Якість відео: {new_q.upper()}")


@router.callback_query(F.data.startswith("set_img_fmt:"))
async def cb_set_img_format(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.data:
        return
    new_fmt = callback.data.split(":", 1)[1].lower()
    prefs = get_user_prefs(callback.from_user.id)
    if prefs.image_format == new_fmt:
        await callback.answer(f"Формат зображень вже {new_fmt.upper()}")
        return
    prefs.image_format = new_fmt
    if callback.message:
        try:
            await callback.message.edit_text(
                _render_settings_text(prefs),
                reply_markup=build_user_settings_keyboard(
                    prefs.quality, prefs.instant_mode, prefs.image_format, prefs.image_max_side
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass
    await callback.answer(f"Формат зображень: {new_fmt.upper()}")


@router.callback_query(F.data.startswith("set_side:"))
async def cb_set_max_side(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.data:
        return
    val = callback.data.split(":", 1)[1]
    prefs = get_user_prefs(callback.from_user.id)
    new_side = int(val) if val.isdigit() else None
    prefs.image_max_side = new_side
    if callback.message:
        try:
            await callback.message.edit_text(
                _render_settings_text(prefs),
                reply_markup=build_user_settings_keyboard(
                    prefs.quality, prefs.instant_mode, prefs.image_format, prefs.image_max_side
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass
    lbl = f"{new_side}px" if new_side else "Оригінал"
    await callback.answer(f"Макс. сторона: {lbl}")


@router.callback_query(F.data == "set_mode:toggle")
async def cb_toggle_mode(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return
    prefs = get_user_prefs(callback.from_user.id)
    prefs.instant_mode = not prefs.instant_mode
    if callback.message:
        try:
            await callback.message.edit_text(
                _render_settings_text(prefs),
                reply_markup=build_user_settings_keyboard(
                    prefs.quality, prefs.instant_mode, prefs.image_format, prefs.image_max_side
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass
    await callback.answer(
        "Увімкнено миттєве завантаження ⚡"
        if prefs.instant_mode
        else "Увімкнено правило 5 секунд ⏱️"
    )

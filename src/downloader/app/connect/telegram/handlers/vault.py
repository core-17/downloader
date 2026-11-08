import html
from pathlib import Path
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from downloader.app.connect.telegram.handlers.delivery import send_single_file
from downloader.app.connect.web.state import downloader

router = Router(name="vault_router")


@router.message(Command("vault", "files"))
async def cmd_vault(message: Message) -> None:
    """Перегляд та масова відправка файлів у чат зі сховища (/vault [тег] [кількість])."""
    raw_args = (message.text or "").split(maxsplit=1)
    args_str = raw_args[1].strip() if len(raw_args) > 1 else ""

    tokens = args_str.split()
    batch_count = None
    if tokens and tokens[-1].isdigit():
        batch_count = max(1, min(20, int(tokens.pop())))
    query = " ".join(tokens).strip().lower().lstrip("#")

    files = await downloader.storage.list_files()
    if query:
        # Підтримка фільтрації за типом медіа: video / image / audio / document / booru
        if query in ("video", "відео", "кліп", "mp4"):
            files = [f for f in files if f.media_type == "video"]
        elif query in ("image", "фото", "картинка", "ілюстрація", "арт"):
            files = [f for f in files if f.media_type == "image"]
        elif query in ("audio", "аудіо", "музика", "пісня", "mp3"):
            files = [f for f in files if f.media_type == "audio"]
        elif query in ("document", "doc", "документ", "pdf"):
            files = [f for f in files if f.media_type == "document"]
        elif query in ("booru", "yande.re", "бору"):
            files = [f for f in files if "yande.re" in f.name.lower() or (f.source_platform and "yande" in f.source_platform.lower()) or "yande.re" in [t.lower() for t in f.tags]]
        else:
            files = [
                f for f in files
                if query in f.name.lower()
                or (f.title and query in f.title.lower())
                or (f.source_platform and query in f.source_platform.lower())
                or any(query in t.lower() for t in f.tags)
            ]

    if not files:
        if query:
            await message.reply(
                f"🔍 У сховищі не знайдено файлів за запитом <code>{html.escape(query)}</code>.",
                parse_mode="HTML",
            )
        else:
            await message.reply(
                "📁 Сховище порожнє. Надішліть посилання чи файл, щоб зберегти його!",
                parse_mode="HTML",
            )
        return

    latest = sorted(files, key=lambda x: x.modified_ts, reverse=True)

    # Якщо користувач вказав кількість для масової відправки (наприклад /vault genshin 5 або /vault 3)
    if batch_count is not None:
        to_send = latest[:batch_count]
        await message.reply(
            f"📤 <b>Масова відправка {len(to_send)} файлів зі сховища в чат...</b>",
            parse_mode="HTML",
        )
        for idx, f in enumerate(to_send, start=1):
            try:
                resolved_path = downloader.storage.resolve_path(f.relative_path)
                await send_single_file(
                    message=message,
                    file_path=resolved_path,
                    caption=f"📁 <b>{html.escape(f.name)}</b> (#{idx}/{len(to_send)})\n💾 Збережено у сховищі",
                    title=f.name,
                )
            except Exception as exc:
                await message.reply(f"❌ Не вдалося надіслати {f.name}: {html.escape(str(exc))}", parse_mode="HTML")
        return

    # Інакше показуємо список з інлайн-кнопками дій та кнопкою надіслати перші 5 шт.
    top_files = latest[:10]
    lines = [f"📁 <b>Файли у сховищі ({len(files)} шт.):</b>\n"]
    buttons = []

    if len(files) > 1:
        # Кнопка швидкої пакетної відправки 5 або 10 файлів за цим запитом
        send_limit = min(5, len(files))
        q_param = query[:20] if query else "all"
        buttons.append([
            InlineKeyboardButton(
                text=f"📦 Надіслати перші {send_limit} шт. в чат",
                callback_data=f"v_batch:{send_limit}:{q_param}",
            )
        ])

    for idx, f in enumerate(top_files, start=1):
        icon = {
            "image": "🖼️",
            "video": "🎬",
            "audio": "🎵",
            "document": "📄",
        }.get(f.media_type, "📦")

        plat = f" [{f.source_platform}]" if f.source_platform else ""
        tags_str = (" " + " ".join(f"#{t}" for t in f.tags[:3])) if f.tags else ""
        lines.append(f"{idx}. {icon} <b>{html.escape(f.name[:35])}</b> ({f.size_mb} MB){plat}{tags_str}")

        cb_key = f.relative_path if len(f.relative_path) <= 45 else f.relative_path[-45:]
        buttons.append([
            InlineKeyboardButton(
                text=f"📤 #{idx} ({f.size_mb} MB)",
                callback_data=f"v_send:{cb_key}",
            ),
            InlineKeyboardButton(
                text=f"🗑️ Видалити",
                callback_data=f"v_del:{cb_key}",
            )
        ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.reply("\n".join(lines), reply_markup=keyboard, parse_mode="HTML")



@router.callback_query(F.data.startswith("v_batch:"))
async def cb_batch_send_vault(callback: CallbackQuery) -> None:
    if not callback.data or not callback.message:
        return
    parts = callback.data.split(":")
    count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 5
    query = parts[2] if len(parts) > 2 and parts[2] != "all" else ""

    files = await downloader.storage.list_files()
    if query:
        # Підтримка фільтрації за типом медіа: video / image / audio / document / booru
        if query in ("video", "відео", "кліп", "mp4"):
            files = [f for f in files if f.media_type == "video"]
        elif query in ("image", "фото", "картинка", "ілюстрація", "арт"):
            files = [f for f in files if f.media_type == "image"]
        elif query in ("audio", "аудіо", "музика", "пісня", "mp3"):
            files = [f for f in files if f.media_type == "audio"]
        elif query in ("document", "doc", "документ", "pdf"):
            files = [f for f in files if f.media_type == "document"]
        elif query in ("booru", "yande.re", "бору"):
            files = [f for f in files if "yande.re" in f.name.lower() or (f.source_platform and "yande" in f.source_platform.lower()) or "yande.re" in [t.lower() for t in f.tags]]
        else:
            files = [
                f for f in files
                if query in f.name.lower()
                or (f.title and query in f.title.lower())
                or (f.source_platform and query in f.source_platform.lower())
                or any(query in t.lower() for t in f.tags)
            ]

    to_send = sorted(files, key=lambda x: x.modified_ts, reverse=True)[:count]
    if not to_send:
        await callback.answer("Файли не знайдено", show_alert=True)
        return

    await callback.answer(f"⏳ Відправляємо {len(to_send)} файлів у чат...")
    for idx, f in enumerate(to_send, start=1):
        try:
            resolved_path = downloader.storage.resolve_path(f.relative_path)
            await send_single_file(
                message=callback.message,
                file_path=resolved_path,
                caption=f"📁 <b>{html.escape(f.name)}</b> (#{idx}/{len(to_send)})\n💾 Збережено у сховищі",
                title=f.name,
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("v_send:"))
async def cb_send_vault_file(callback: CallbackQuery) -> None:
    if not callback.data:
        return
    key = callback.data.split(":", 1)[1]
    files = await downloader.storage.list_files()
    target = next((f for f in files if f.relative_path.endswith(key) or f.name == key), None)
    if not target:
        await callback.answer("Файл не знайдено у сховищі", show_alert=True)
        return

    await callback.answer("⏳ Відправляємо файл...")
    try:
        resolved_path = downloader.storage.resolve_path(target.relative_path)
        if callback.message:
            await send_single_file(
                message=callback.message,
                file_path=resolved_path,
                caption=f"📁 <b>{html.escape(target.name)}</b>\n💾 Збережено у сховищі",
                title=target.name,
            )
    except Exception as exc:
        if callback.message:
            await callback.message.reply(f"❌ Помилка: {html.escape(str(exc))}", parse_mode="HTML")


@router.callback_query(F.data.startswith("v_del:"))
async def cb_delete_vault_file(callback: CallbackQuery) -> None:
    if not callback.data:
        return
    key = callback.data.split(":", 1)[1]
    files = await downloader.storage.list_files()
    target = next((f for f in files if f.relative_path.endswith(key) or f.name == key), None)
    if not target:
        await callback.answer("Файл не знайдено у сховищі", show_alert=True)
        return

    success = await downloader.storage.delete_file(target.relative_path)
    if success:
        await callback.answer(f"🗑️ Файл {target.name[:25]} видалено!", show_alert=True)
        if callback.message:
            await callback.message.edit_text(
                f"🗑️ Файл <code>{html.escape(target.name)}</code> успішно видалено зі сховища.",
                parse_mode="HTML",
            )
    else:
        await callback.answer("Не вдалося видалити файл", show_alert=True)



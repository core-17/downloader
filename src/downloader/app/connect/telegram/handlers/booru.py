import html
from pathlib import Path
import uuid

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from downloader.app.config.constants import IMAGE_EXTENSIONS
from downloader.app.connect.telegram.handlers.delivery import (
    deliver_files_to_chat,
    safe_react,
    sync_progress,
)
from downloader.app.connect.telegram.handlers.settings import get_user_prefs
from downloader.app.connect.web.state import downloader as dispatcher
from downloader.app.core.dto.task import TaskStatus
from downloader.app.service.compression.transcoder import process_image

router = Router(name="booru_router")


@router.message(Command("booru"))
async def cmd_booru(message: Message) -> None:
    """Команда /booru <теги> [кількість] для завантаження з Yande.re прямо в Telegram."""
    raw = (message.text or "").strip()
    parts = raw.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply(
            "🌸 <b>Завантаження з Yande.re Booru</b>\n\n"
            "Приклади використання:\n"
            "• <code>/booru landscape 5</code> — скачати 5 ілюстрацій за тегом landscape\n"
            "• <code>/booru order:score sky 10</code> — 10 найкращих за тегом sky\n"
            "• Або просто напишіть у повідомленні: <code>booru:genshin_impact</code>",
            parse_mode="HTML",
        )
        return

    arg_tokens = parts[1].strip().split()
    limit = 5
    if len(arg_tokens) > 1 and arg_tokens[-1].isdigit():
        limit = max(1, min(20, int(arg_tokens.pop())))

    booru_tags = " ".join(arg_tokens)
    user_id = message.from_user.id if message.from_user else 0
    prefs = get_user_prefs(user_id)
    task_id = str(uuid.uuid4())[:8]

    await safe_react(message, "👀")
    status_msg = await message.reply(
        f"🌸 <b>Пошук на Yande.re за тегами:</b> <code>{html.escape(booru_tags)}</code> ({limit} шт.)...",
        parse_mode="HTML",
    )

    page_media = await dispatcher.booru_service.fetch_posts(tags=booru_tags, limit=limit)
    if not page_media or not page_media.items:
        await status_msg.edit_text(
            f"❌ За тегами <code>{html.escape(booru_tags)}</code> на Yande.re нічого не знайдено.",
            parse_mode="HTML",
        )
        return

    res = await dispatcher.direct.download_items(
        task_id=task_id,
        source_url=f"https://yande.re/post?tags={booru_tags}",
        items=page_media.items,
        title=page_media.title,
        description=page_media.description,
        source_platform="Yande.re",
    )

    fmt = (prefs.image_format or "original").lower().strip()
    if fmt != "original" and res.file_paths:
        new_paths = []
        for p_str in res.file_paths:
            p = Path(p_str)
            if p.suffix.lower() in IMAGE_EXTENSIONS:
                processed = await process_image(p, target_format=fmt, max_side=prefs.image_max_side)
                new_paths.append(str(processed))
            else:
                new_paths.append(str(p))
        res.file_paths = new_paths
        if new_paths:
            res.file_path = new_paths[0]

    res.tags = ["yande.re", *[t for t in booru_tags.split() if t]]
    await dispatcher.storage.save_task_metadata(task_id, res)
    await sync_progress(res)

    if res.status == TaskStatus.COMPLETED and res.file_paths:
        try:
            await status_msg.edit_text(f"📤 <b>Відправка {len(res.file_paths)} ілюстрацій...</b>", parse_mode="HTML")
        except Exception:
            pass
        await deliver_files_to_chat(message, res)
        await safe_react(message, "👍")
        try:
            await status_msg.delete()
        except Exception:
            pass
    else:
        await status_msg.edit_text(
            f"❌ Помилка завантаження з Yande.re: {html.escape(res.error or 'невідома помилка')}",
            parse_mode="HTML",
        )


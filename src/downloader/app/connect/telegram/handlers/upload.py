import asyncio
import html
from pathlib import Path
import uuid

from aiogram import F, Router
from aiogram.types import Message

from downloader.app.config.constants import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
)
from downloader.app.config.settings import get_settings
from downloader.app.connect.telegram.handlers.delivery import (
    extract_urls_and_tags,
    safe_react,
    sync_progress,
)
from downloader.app.connect.telegram.handlers.link import process_single_url
from downloader.app.connect.telegram.handlers.settings import get_user_prefs
from downloader.app.connect.web.state import downloader as dispatcher
from downloader.app.core.dto.task import TaskProgress, TaskStatus
from downloader.app.service.compression.transcoder import process_image
from downloader.app.service.download.base import sanitize_filename

router = Router(name="upload_router")
_settings = get_settings()


@router.message(F.photo | F.video | F.audio | F.document | F.animation)
async def handle_direct_media_upload(message: Message) -> None:
    """Збереження прямо надісланих у бот картинок, відео, аудіо та документів у сховище (підтримка посилань у caption)."""
    urls, tags = extract_urls_and_tags(message)
    if urls:
        for u in urls:
            asyncio.create_task(process_single_url(message, u, tags, skip_timer=True))

    await safe_react(message, "👀")
    user_id = message.from_user.id if message.from_user else 0
    prefs = get_user_prefs(user_id)
    task_id = str(uuid.uuid4())[:8]

    task_dir = _settings.DOWNLOAD_TEMP_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    bot = message.bot
    if not bot:
        return

    file_id = None
    orig_name = None
    media_type = "image"
    file_size = 0

    if message.photo:
        photo = message.photo[-1]
        file_id = photo.file_id
        orig_name = f"photo_{photo.file_unique_id}.jpg"
        media_type = "image"
        file_size = photo.file_size or 0
    elif message.video:
        file_id = message.video.file_id
        orig_name = message.video.file_name or f"video_{message.video.file_unique_id}.mp4"
        media_type = "video"
        file_size = message.video.file_size or 0
    elif message.animation:
        file_id = message.animation.file_id
        orig_name = message.animation.file_name or f"gif_{message.animation.file_unique_id}.mp4"
        media_type = "video"
        file_size = message.animation.file_size or 0
    elif message.audio:
        file_id = message.audio.file_id
        orig_name = message.audio.file_name or f"audio_{message.audio.file_unique_id}.mp3"
        media_type = "audio"
        file_size = message.audio.file_size or 0
    elif message.document:
        file_id = message.document.file_id
        orig_name = message.document.file_name or f"doc_{message.document.file_unique_id}"
        ext = Path(orig_name).suffix.lower()
        if ext in IMAGE_EXTENSIONS:
            media_type = "image"
        elif ext in VIDEO_EXTENSIONS:
            media_type = "video"
        elif ext in AUDIO_EXTENSIONS:
            media_type = "audio"
        else:
            media_type = "document"
        file_size = message.document.file_size or 0

    if not file_id or not orig_name:
        return

    raw_path = Path(orig_name)
    safe_stem = sanitize_filename(raw_path.stem, max_len=80)
    safe_ext = raw_path.suffix or ".bin"
    safe_filename = f"{safe_stem}{safe_ext}"

    status_msg = await message.reply("⏳ <b>Збереження надісланого файлу у сховище...</b>", parse_mode="HTML")
    dest_path = task_dir / safe_filename

    try:
        tg_file = await bot.get_file(file_id)
        if tg_file.file_path:
            await bot.download_file(tg_file.file_path, destination=dest_path)

        fmt = (prefs.image_format or "original").lower().strip()
        if (fmt != "original" or prefs.image_max_side) and dest_path.suffix.lower() in IMAGE_EXTENSIONS:
            dest_path = await process_image(dest_path, target_format=fmt, max_side=prefs.image_max_side)
            safe_filename = dest_path.name

        actual_size = dest_path.stat().st_size if dest_path.exists() else file_size
        mb_val = round(actual_size / (1024 * 1024), 2) if actual_size else 0.0

        prog = TaskProgress(
            task_id=task_id,
            url="telegram:upload",
            status=TaskStatus.COMPLETED,
            media_type=media_type,
            source_platform="Telegram",
            title=safe_filename,
            file_path=str(dest_path),
            file_paths=[str(dest_path)],
            tags=tags,
            percent=100.0,
            downloaded_mb=mb_val,
            total_mb=mb_val,
        )
        await dispatcher.storage.save_task_metadata(task_id, prog)
        await sync_progress(prog)
        await safe_react(message, "👍")

        tags_str = ("\n🏷️ " + " ".join(f"#{t}" for t in tags)) if tags else ""
        if status_msg:
            await status_msg.edit_text(
                f"✅ <b>Файл збережено в медіа-архів!</b>\n"
                f"📁 <code>{html.escape(safe_filename)}</code> ({mb_val} MB){tags_str}",
                parse_mode="HTML",
            )
    except Exception as exc:
        await safe_react(message, "😢")
        if status_msg:
            await status_msg.edit_text(f"❌ <b>Помилка збереження файлу:</b> {html.escape(str(exc))}", parse_mode="HTML")


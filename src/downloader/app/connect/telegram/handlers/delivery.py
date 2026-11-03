import html
from pathlib import Path
import re

from aiogram.types import (
    FSInputFile,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
    ReactionTypeEmoji,
)

from downloader.app.config.constants import (
    AUDIO_EXTENSIONS,
    HASHTAG_REGEX,
    TELEGRAM_MAX_BOT_API_FILE_BYTES,
    TELEGRAM_MAX_PHOTO_BYTES,
    URL_REGEX,
    VIDEO_EXTENSIONS,
)
from downloader.app.connect.telegram.handlers.search import record_task
from downloader.app.connect.web.state import broadcast_progress
from downloader.app.core.dto.task import TaskProgress

BOORU_INLINE_REGEX = re.compile(r"\b(?:booru|yande\.re):[^\s<>\"']+", re.IGNORECASE)
TELEGRAM_SAFE_PHOTO_EXTS = {".jpg", ".jpeg", ".png"}
TELEGRAM_SAFE_PHOTO_MAX_BYTES = min(TELEGRAM_MAX_PHOTO_BYTES, 8 * 1024 * 1024)


async def sync_progress(prog: TaskProgress) -> None:
    """Синхронізує прогрес задачі між Telegram-ботом та веб-інтерфейсом (WebSocket)."""
    record_task(prog)
    try:
        await broadcast_progress(prog)
    except Exception:
        pass


async def safe_react(message: Message, emoji: str) -> None:
    try:
        await message.react([ReactionTypeEmoji(emoji=emoji)])
    except Exception:
        pass


def can_send_as_telegram_photo(file_path: Path) -> bool:
    ext = file_path.suffix.lower()
    if ext not in TELEGRAM_SAFE_PHOTO_EXTS:
        return False
    try:
        return file_path.stat().st_size <= TELEGRAM_SAFE_PHOTO_MAX_BYTES
    except OSError:
        return False


def extract_urls_and_tags(message: Message) -> tuple[list[str], list[str]]:
    raw_text = (message.text or message.caption or "").strip()
    urls: list[str] = []
    for m in URL_REGEX.findall(raw_text):
        cleaned = m.rstrip(".,;:!?)>]}")
        if cleaned not in urls:
            urls.append(cleaned)

    for bm in BOORU_INLINE_REGEX.findall(raw_text):
        cleaned = bm.rstrip(".,;:!?)>]}")
        if cleaned not in urls:
            urls.append(cleaned)

    entities = (message.entities or []) + (message.caption_entities or [])
    for ent in entities:
        if ent.type == "text_link" and ent.url and ent.url.startswith("http"):
            if ent.url not in urls:
                urls.append(ent.url)

    tags = []
    for tag in HASHTAG_REGEX.findall(raw_text):
        if tag not in tags:
            tags.append(tag)
    return urls, tags


def format_caption(progress: TaskProgress) -> str:
    title = html.escape((progress.title or "Медіафайл")[:180])
    platform = f" [{html.escape(progress.source_platform)}]" if progress.source_platform else ""
    tags_line = ""
    if progress.tags:
        tags_line = "\n🏷️ " + " ".join(f"#{html.escape(t)}" for t in progress.tags[:12])
    return (
        f"<b>{title}</b>{platform}\n"
        f"🔗 <a href=\"{html.escape(progress.url)}\">Оригінал</a>"
        f"{tags_line}"
    )


async def deliver_files_to_chat(message: Message, progress: TaskProgress) -> None:
    file_paths = [Path(p) for p in progress.file_paths if Path(p).exists()]
    if not file_paths and progress.file_path and Path(progress.file_path).exists():
        file_paths = [Path(progress.file_path)]

    if not file_paths:
        await message.reply("❌ Файл не знайдено після завантаження.")
        return

    caption = format_caption(progress)

    oversized = [p for p in file_paths if p.stat().st_size > TELEGRAM_MAX_BOT_API_FILE_BYTES]
    sendable = [p for p in file_paths if p.stat().st_size <= TELEGRAM_MAX_BOT_API_FILE_BYTES]

    if oversized:
        paths_info = "\n".join(
            f"• <code>{html.escape(str(p))}</code> ({round(p.stat().st_size / (1024 * 1024), 1)} MB)"
            for p in oversized
        )
        await message.reply(
            f"💾 <b>Файл перевищує ліміт Telegram Bot API (50 МБ) і збережений у локальному сховищі:</b>\n"
            f"{paths_info}\n\n{caption}",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    if not sendable:
        return

    if len(sendable) > 1:
        for chunk_idx in range(0, len(sendable), 10):
            batch = sendable[chunk_idx : chunk_idx + 10]
            all_photo_or_video = all(
                can_send_as_telegram_photo(p) or p.suffix.lower() in VIDEO_EXTENSIONS
                for p in batch
            )
            media_group = []
            for idx, p in enumerate(batch):
                ext = p.suffix.lower()
                item_caption = caption if (chunk_idx == 0 and idx == 0) else None
                input_file = FSInputFile(p)
                if all_photo_or_video and can_send_as_telegram_photo(p):
                    media_group.append(
                        InputMediaPhoto(
                            media=input_file,
                            caption=item_caption,
                            parse_mode="HTML" if item_caption else None,
                        )
                    )
                elif all_photo_or_video and ext in VIDEO_EXTENSIONS:
                    media_group.append(
                        InputMediaVideo(
                            media=input_file,
                            caption=item_caption,
                            parse_mode="HTML" if item_caption else None,
                            supports_streaming=True,
                        )
                    )
                else:
                    media_group.append(
                        InputMediaDocument(
                            media=input_file,
                            caption=item_caption,
                            parse_mode="HTML" if item_caption else None,
                        )
                    )
            try:
                await message.reply_media_group(media=media_group, disable_notification=True)
                continue
            except Exception:
                pass

            for idx, p in enumerate(batch):
                await send_single_file(
                    message,
                    p,
                    caption if (chunk_idx == 0 and idx == 0) else None,
                    progress.title,
                )
        return

    await send_single_file(message, sendable[0], caption, progress.title)


async def send_single_file(
    message: Message,
    file_path: Path,
    caption: str | None,
    title: str | None = None,
) -> None:
    ext = file_path.suffix.lower()
    parse_mode = "HTML" if caption else None

    try:
        if ext == ".gif":
            await message.reply_animation(
                animation=FSInputFile(file_path),
                caption=caption,
                parse_mode=parse_mode,
                disable_notification=True,
            )
            return

        if can_send_as_telegram_photo(file_path):
            try:
                await message.reply_photo(
                    photo=FSInputFile(file_path),
                    caption=caption,
                    parse_mode=parse_mode,
                    disable_notification=True,
                )
                return
            except Exception:
                await message.reply_document(
                    document=FSInputFile(file_path),
                    caption=caption,
                    parse_mode=parse_mode,
                    disable_notification=True,
                )
                return

        if ext in VIDEO_EXTENSIONS:
            try:
                await message.reply_video(
                    video=FSInputFile(file_path),
                    caption=caption,
                    parse_mode=parse_mode,
                    supports_streaming=True,
                    disable_notification=True,
                )
                return
            except Exception:
                await message.reply_document(
                    document=FSInputFile(file_path),
                    caption=caption,
                    parse_mode=parse_mode,
                    disable_notification=True,
                )
                return

        if ext in AUDIO_EXTENSIONS:
            await message.reply_audio(
                audio=FSInputFile(file_path),
                caption=caption,
                title=title or file_path.stem,
                parse_mode=parse_mode,
                disable_notification=True,
            )
            return

        await message.reply_document(
            document=FSInputFile(file_path),
            caption=caption,
            parse_mode=parse_mode,
            disable_notification=True,
        )
    except Exception as exc:
        await message.reply(f"❌ Помилка відправки файлу в Telegram: {html.escape(str(exc))}", parse_mode="HTML")


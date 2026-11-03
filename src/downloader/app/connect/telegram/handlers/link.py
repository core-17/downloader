import asyncio
from dataclasses import dataclass, field
import html
import time
import uuid

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from downloader.app.config.settings import get_settings
from downloader.app.connect.telegram.handlers.delivery import (
    deliver_files_to_chat,
    extract_urls_and_tags,
    safe_react,
    sync_progress,
)
from downloader.app.connect.telegram.handlers.settings import get_user_prefs
from downloader.app.connect.telegram.keyboards.timer_kb import (
    build_task_quality_keyboard,
    build_timer_keyboard,
)
from downloader.app.connect.web.state import downloader as dispatcher
from downloader.app.core.dto.task import TaskProgress, TaskStatus

router = Router(name="link_router")
_settings = get_settings()


@dataclass
class PendingLinkTask:
    task_id: str
    url: str
    tags: list[str]
    max_height: int
    image_format: str = "original"
    image_max_side: int | None = None
    audio_only: bool = False
    cancelled: bool = False
    configuring: bool = False
    start_event: asyncio.Event = field(default_factory=asyncio.Event)
    config_event: asyncio.Event = field(default_factory=asyncio.Event)


_pending_tasks: dict[str, PendingLinkTask] = {}


async def process_single_url(
    message: Message,
    url: str,
    tags: list[str],
    skip_timer: bool = False,
) -> None:
    user_id = message.from_user.id if message.from_user else 0
    prefs = get_user_prefs(user_id)
    task_id = str(uuid.uuid4())[:8]
    timeout_sec = _settings.CONFIRMATION_TIMEOUT_SECONDS

    pending = PendingLinkTask(
        task_id=task_id,
        url=url,
        tags=tags,
        max_height=prefs.max_height,
        image_format=prefs.image_format,
        image_max_side=prefs.image_max_side,
        audio_only=False,
    )
    _pending_tasks[task_id] = pending

    status_msg: Message | None = None
    try:
        if not skip_timer and not prefs.instant_mode and timeout_sec > 0:
            tags_preview = (" | 🏷️ " + " ".join(f"#{t}" for t in tags)) if tags else ""
            status_msg = await message.reply(
                f"👀 <b>Посилання прийнято</b> (відео: <b>{prefs.quality.upper()}</b>, фото: <b>{prefs.image_format.upper()}</b>{tags_preview})\n"
                f"⏱️ Автоматичний старт завантаження через <b>{timeout_sec} сек</b>...",
                reply_markup=build_timer_keyboard(task_id, seconds=timeout_sec),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )

            try:
                await asyncio.wait_for(pending.start_event.wait(), timeout=timeout_sec)
            except asyncio.TimeoutError:
                pass

            if pending.configuring and not pending.cancelled:
                try:
                    await asyncio.wait_for(pending.config_event.wait(), timeout=60)
                except asyncio.TimeoutError:
                    pass

            if pending.cancelled:
                if status_msg:
                    await status_msg.edit_text("❌ <b>Завантаження скасовано.</b>", parse_mode="HTML")
                return
        else:
            status_msg = await message.reply(
                "⏳ <b>Аналіз посилання та підготовка завантаження...</b>",
                parse_mode="HTML",
            )

        last_edit_ts = 0.0
        last_text = ""

        async def on_progress(prog: TaskProgress) -> None:
            nonlocal last_edit_ts, last_text
            await sync_progress(prog)
            if not status_msg:
                return
            now = time.monotonic()
            if prog.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED) and (now - last_edit_ts < 1.8):
                return

            title_str = html.escape((prog.title or prog.url)[:70])
            if prog.status == TaskStatus.EXTRACTING:
                text = f"🔍 <b>Отримання метаданих...</b>\n<code>{title_str}</code>"
            elif prog.status == TaskStatus.DOWNLOADING:
                total_str = f" / {prog.total_mb} MB" if prog.total_mb else ""
                speed_str = f" | 🚀 {prog.speed_mb_s} MB/s" if prog.speed_mb_s else ""
                text = (
                    f"⬇️ <b>Завантаження ({prog.percent}%):</b> <code>{title_str}</code>\n"
                    f"📦 {prog.downloaded_mb}{total_str} MB{speed_str}"
                )
            elif prog.status == TaskStatus.PROCESSING:
                text = f"⚙️ <b>Обробка та склеювання медіа...</b>\n<code>{title_str}</code>"
            else:
                return

            if text != last_text:
                last_text = text
                last_edit_ts = now
                try:
                    await status_msg.edit_text(text, parse_mode="HTML", disable_web_page_preview=True)
                except Exception:
                    pass

        result = await dispatcher.download(
            task_id=task_id,
            url=url,
            max_height=pending.max_height,
            audio_only=pending.audio_only,
            on_progress=on_progress,
            tags=tags,
            image_format=pending.image_format,
            image_max_side=pending.image_max_side,
        )
        await sync_progress(result)

        if result.status == TaskStatus.COMPLETED and (result.file_path or result.file_paths):
            if status_msg:
                try:
                    await status_msg.edit_text("📤 <b>Відправка файлу в чат...</b>", parse_mode="HTML")
                except Exception:
                    pass

            await deliver_files_to_chat(message, result)
            await safe_react(message, "👍")

            if status_msg:
                try:
                    await status_msg.delete()
                except Exception:
                    pass
        else:
            await safe_react(message, "😢")
            err_msg = html.escape(result.error or "Невідома помилка завантаження")
            if status_msg:
                await status_msg.edit_text(
                    f"❌ <b>Не вдалося завантажити медіа:</b>\n<code>{err_msg[:350]}</code>",
                    parse_mode="HTML",
                )
            else:
                await message.reply(
                    f"❌ <b>Не вдалося завантажити медіа:</b>\n<code>{err_msg[:350]}</code>",
                    parse_mode="HTML",
                )
    finally:
        _pending_tasks.pop(task_id, None)


@router.callback_query(F.data.startswith("dl_now:"))
async def cb_download_now(callback: CallbackQuery) -> None:
    if not callback.data:
        return
    task_id = callback.data.split(":", 1)[1]
    pending = _pending_tasks.get(task_id)
    if not pending:
        await callback.answer("Задача вже запущена або завершена")
        return
    pending.configuring = False
    pending.start_event.set()
    pending.config_event.set()
    await callback.answer("🚀 Запускаємо завантаження!")


@router.callback_query(F.data.startswith("dl_cfg:"))
async def cb_configure_task(callback: CallbackQuery) -> None:
    if not callback.data:
        return
    task_id = callback.data.split(":", 1)[1]
    pending = _pending_tasks.get(task_id)
    if not pending:
        await callback.answer("Задача вже запущена")
        return
    pending.configuring = True
    pending.start_event.set()
    if callback.message:
        await callback.message.edit_text(
            "⚙️ <b>Оберіть якість або формат для цього завантаження:</b>",
            reply_markup=build_task_quality_keyboard(task_id),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("dl_q:"))
async def cb_select_task_quality(callback: CallbackQuery) -> None:
    if not callback.data:
        return
    parts = callback.data.split(":")
    if len(parts) < 3:
        return
    task_id, choice = parts[1], parts[2]
    pending = _pending_tasks.get(task_id)
    if not pending:
        await callback.answer("Задача вже запущена")
        return

    if choice == "audio":
        pending.audio_only = True
        label = "🎵 MP3 Аудіо"
    else:
        pending.audio_only = False
        pending.max_height = int(choice) if choice.isdigit() else 1080
        label = f"🎬 {pending.max_height}p"

    pending.configuring = False
    pending.start_event.set()
    pending.config_event.set()
    await callback.answer(f"Обрано: {label}")


@router.callback_query(F.data.startswith("dl_cancel:"))
async def cb_cancel_task(callback: CallbackQuery) -> None:
    if not callback.data:
        return
    task_id = callback.data.split(":", 1)[1]
    pending = _pending_tasks.get(task_id)
    if not pending:
        await callback.answer("Вже неактуально")
        return
    pending.cancelled = True
    pending.configuring = False
    pending.start_event.set()
    pending.config_event.set()
    await callback.answer("Скасовано ❌")


@router.message(F.text | F.caption)
async def handle_incoming_links(message: Message) -> None:
    urls, tags = extract_urls_and_tags(message)
    if not urls:
        return

    await safe_react(message, "👀")

    skip_timer = len(urls) > 1
    for url in urls:
        asyncio.create_task(process_single_url(message, url, tags, skip_timer=skip_timer))

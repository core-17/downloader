import html
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from downloader.app.core.dto.task import TaskProgress

router = Router(name="search_router")

# Локальний реєстр виконаних та активних задач для швидкого пошуку в боті
recent_tasks: dict[str, TaskProgress] = {}


def record_task(progress: TaskProgress) -> None:
    recent_tasks[progress.task_id] = progress


@router.message(Command("tasks", "history", "search"))
async def cmd_tasks(message: Message) -> None:
    text_parts = (message.text or "").split(maxsplit=1)
    query = text_parts[1].strip().lstrip("#").lower() if len(text_parts) > 1 else ""

    items = list(recent_tasks.values())
    if query:
        items = [
            t
            for t in items
            if query in (t.title or "").lower()
            or query in t.url.lower()
            or query in (t.media_type or "").lower()
            or any(query in tag.lower() for tag in t.tags)
        ]

    if not items:
        if query:
            await message.answer(f"🔍 За запитом <code>{html.escape(query)}</code> нічого не знайдено.", parse_mode="HTML")
        else:
            await message.answer("📭 Історія завантажень поки порожня. Надішліть посилання, щоб почати!")
        return

    lines = ["📋 <b>Останні завантаження:</b>\n"]
    for t in reversed(items[-15:]):
        icon = {
            "video": "🎬",
            "image": "🖼️",
            "gallery": "🖼️",
            "audio": "🎵",
            "document": "📄",
        }.get(t.media_type, "📦")
        status_badge = "✅" if t.status.value == "completed" else ("❌" if t.status.value == "failed" else "⏳")
        title = html.escape((t.title or t.url)[:60])
        tags_str = " ".join(f"#{html.escape(tag)}" for tag in t.tags)
        size_str = f"{t.downloaded_mb} MB" if t.downloaded_mb else ""
        lines.append(
            f"{status_badge} {icon} <b>{title}</b> ({size_str})\n"
            f"   🔗 <a href=\"{html.escape(t.url)}\">Джерело</a> {tags_str}"
        )

    await message.answer("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)


import html
from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from downloader.app.connect.web.state import downloader

router = Router(name="inline_router")


@router.inline_query()
async def inline_tag_suggestions(query: InlineQuery) -> None:
    """
    Інлайн-підказки тегів сховища при наборі @BotName [тег].
    Користувач бачить список знайдених тегів та кількість файлів за ними.
    """
    raw_q = (query.query or "").strip().lower().lstrip("#")
    files = await downloader.storage.list_files()

    tag_counts: dict[str, int] = {}
    for f in files:
        for t in f.tags:
            clean_t = str(t).lower().lstrip("#")
            tag_counts[clean_t] = tag_counts.get(clean_t, 0) + 1

    matched_tags = [
        (t, count)
        for t, count in tag_counts.items()
        if not raw_q or raw_q in t
    ]
    # Спочатку теги з найбільшою кількістю файлів
    matched_tags.sort(key=lambda x: x[1], reverse=True)
    top_matches = matched_tags[:25]

    results = []
    for idx, (tag, count) in enumerate(top_matches):
        results.append(
            InlineQueryResultArticle(
                id=f"tag_{idx}_{tag}",
                title=f"#{tag} ({count} файлів)",
                description=f"Надіслати команду для перегляду та експорту тегу #{tag}",
                input_message_content=InputTextMessageContent(
                    message_text=f"/vault {tag} 5",
                    parse_mode=None,
                ),
            )
        )

    # Якщо нічого не знайдено за фільтром, пропонуємо загальні команди
    if not results:
        results.append(
            InlineQueryResultArticle(
                id="default_vault",
                title="📁 Моє Сховище",
                description="Показати останні збережені файли",
                input_message_content=InputTextMessageContent(
                    message_text="/vault",
                ),
            )
        )

    await query.answer(results=results, cache_time=15, is_personal=True)


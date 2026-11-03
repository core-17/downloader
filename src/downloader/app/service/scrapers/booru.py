import logging
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse
import aiohttp

from downloader.app.config.constants import DEFAULT_HTTP_HEADERS
from downloader.app.core.dto.media import ExtractedMediaItem, ExtractedPageMedia, MediaType
from downloader.app.service.scrapers.base import BaseScraper

logger = logging.getLogger("downloader.booru")

# Вбудовані мета-теги та популярні теги Yande.re для миттєвих підказок навіть при порожньому вводі
DEFAULT_BOORU_TAG_SUGGESTIONS: list[dict[str, Any]] = [
    {"name": "order:score", "count": 999999, "type": -1, "type_label": " Сортування"},
    {"name": "order:mpixels", "count": 888888, "type": -1, "type_label": "Сортування"},
    {"name": "rating:safe", "count": 777777, "type": -1, "type_label": "Фільтр"},
    {"name": "landscape", "count": 48500, "type": 0, "type_label": "Загальний"},
    {"name": "scenery", "count": 62000, "type": 0, "type_label": "Загальний"},
    {"name": "sky", "count": 75000, "type": 0, "type_label": "Загальний"},
    {"name": "clouds", "count": 54000, "type": 0, "type_label": "Загальний"},
    {"name": "original", "count": 195000, "type": 3, "type_label": "Оригінал"},
    {"name": "wallpaper", "count": 41000, "type": 0, "type_label": "Загальний"},
    {"name": "night", "count": 29000, "type": 0, "type_label": "Загальний"},
    {"name": "water", "count": 46000, "type": 0, "type_label": "Загальний"},
    {"name": "sunset", "count": 18500, "type": 0, "type_label": "Загальний"},
    {"name": "genshin_impact", "count": 38000, "type": 3, "type_label": "Тайтл"},
    {"name": "blue_archive", "count": 27000, "type": 3, "type_label": "Тайтл"},
    {"name": "fate/grand_order", "count": 44000, "type": 3, "type_label": "Тайтл"},
    {"name": "touhou", "count": 92000, "type": 3, "type_label": "Тайтл"},
    {"name": "arknights", "count": 24000, "type": 3, "type_label": "Тайтл"},
    {"name": "honkai:_star_rail", "count": 14000, "type": 3, "type_label": "Тайтл"},
    {"name": "vocaloid", "count": 36000, "type": 3, "type_label": "Тайтл"},
]

TAG_TYPE_LABELS: dict[int, str] = {
    -1: "Мета-тег",
    0: "Загальний",
    1: "Художник",
    3: "Тайтл",
    4: "Персонаж",
    5: "Студія",
    6: "Інше",
}


class BooruService(BaseScraper):
    """
    Сервіс для пошуку та завантаження ілюстрацій з Booru-сервісів (Yande.re).
    Підтримує пошук за тегами, автодоповнення тегів, вибір кількості результатів та отримання оригіналів.
    """

    def __init__(self, base_url: str = "https://yande.re"):
        self.base_url = base_url.rstrip("/")

    async def extract(self, url: str) -> ExtractedPageMedia | None:
        """
        Підтримує прямі посилання на Yande.re:
        - https://yande.re/post/show/<id>
        - https://yande.re/post?tags=<tags>
        """
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        if "yande.re" not in host:
            return None

        path = parsed.path.rstrip("/")
        if "/post/show/" in path:
            post_id = path.split("/post/show/")[-1].split("/")[0]
            if post_id.isdigit():
                posts = await self.fetch_posts(tags=f"id:{post_id}", limit=1)
                if posts and posts.items:
                    return posts

        query_params = parse_qs(parsed.query)
        if "tags" in query_params and query_params["tags"]:
            tags_str = query_params["tags"][0]
            posts = await self.fetch_posts(tags=tags_str, limit=10)
            if posts and posts.items:
                return posts

        return None

    async def search_tags(self, query: str = "", limit: int = 12) -> list[dict[str, Any]]:
        """
        Повертає список підказок тегів Yande.re для автодоповнення при вводі.
        Використовує офіційний ендпоінт https://yande.re/tag.json?name=...&order=count
        та вбудовані мета-теги.
        """
        q = query.strip().lower().lstrip("#")
        limit = max(1, min(limit, 30))

        if not q:
            return DEFAULT_BOORU_TAG_SUGGESTIONS[:limit]

        results: list[dict[str, Any]] = []
        seen_names: set[str] = set()

        # 1. Спочатку перевіряємо мета-теги та популярні базові теги
        for item in DEFAULT_BOORU_TAG_SUGGESTIONS:
            name = item["name"].lower()
            if name.startswith(q) or q in name:
                results.append(item)
                seen_names.add(name)

        # 2. Запит до офіційного API Yande.re /tag.json
        encoded_q = quote_plus(q)
        endpoint = f"{self.base_url}/tag.json?name={encoded_q}&order=count&limit=40"
        timeout = aiohttp.ClientTimeout(total=8, connect=5)
        headers = dict(DEFAULT_HTTP_HEADERS)
        headers["Referer"] = f"{self.base_url}/"

        try:
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(endpoint) as resp:
                    if resp.status == 200:
                        raw_tags: list[dict[str, Any]] = await resp.json()
                        if isinstance(raw_tags, list):
                            # Сортуємо так, щоб теги, які починаються з введеного префікса, йшли першими за популярністю
                            starts_with = []
                            contains = []
                            for t in raw_tags:
                                t_name = str(t.get("name") or "").strip()
                                if not t_name or t_name.lower() in seen_names:
                                    continue
                                t_type = int(t.get("type", 0))
                                entry = {
                                    "name": t_name,
                                    "count": int(t.get("count", 0)),
                                    "type": t_type,
                                    "type_label": TAG_TYPE_LABELS.get(t_type, "Загальний"),
                                }
                                if t_name.lower().startswith(q):
                                    starts_with.append(entry)
                                else:
                                    contains.append(entry)

                            starts_with.sort(key=lambda x: x["count"], reverse=True)
                            contains.sort(key=lambda x: x["count"], reverse=True)
                            for entry in starts_with + contains:
                                seen_names.add(entry["name"].lower())
                                results.append(entry)
                                if len(results) >= limit:
                                    break
        except Exception as exc:
            logger.debug("Не вдалося отримати підказки тегів з Yande.re API: %s", exc)

        return results[:limit]

    async def fetch_raw_posts(
        self,
        tags: str = "",
        limit: int = 20,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """Отримує структурований список постів Yande.re для клієнтського браузера."""
        limit = max(1, min(limit, 100))
        encoded_tags = quote_plus(tags.strip())
        endpoint = f"{self.base_url}/post.json?tags={encoded_tags}&limit={limit}&page={page}"

        timeout = aiohttp.ClientTimeout(total=20, connect=10)
        headers = dict(DEFAULT_HTTP_HEADERS)
        headers["Referer"] = f"{self.base_url}/"

        try:
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(endpoint) as resp:
                    if resp.status == 200:
                        posts: list[dict[str, Any]] = await resp.json()
                        cleaned = []
                        for p in posts:
                            orig_url = p.get("file_url") or p.get("jpeg_url") or p.get("sample_url")
                            if not orig_url:
                                continue
                            post_id = p.get("id")
                            cleaned.append({
                                "id": post_id,
                                "tags": p.get("tags", ""),
                                "rating": p.get("rating", "s"),
                                "score": p.get("score", 0),
                                "width": p.get("width", 0),
                                "height": p.get("height", 0),
                                "file_size": p.get("file_size", 0),
                                "file_ext": p.get("file_ext", "jpg"),
                                "preview_url": p.get("preview_url") or p.get("sample_url") or orig_url,
                                "sample_url": p.get("sample_url") or orig_url,
                                "file_url": orig_url,
                                "post_url": f"{self.base_url}/post/show/{post_id}",
                                "source": p.get("source", ""),
                            })
                        return cleaned
        except Exception as exc:
            logger.error("Помилка отримання постів Booru: %s", exc)
        return []

    async def fetch_all_posts_by_tag(
        self,
        tags: str,
        max_pages: int = 10,
        per_page: int = 100,
    ) -> ExtractedPageMedia:
        """Посторінково витягує всі доступні пости за тегом до вичерпання або max_pages."""
        all_items: list[ExtractedMediaItem] = []
        seen_ids: set[int] = set()

        for page in range(1, max_pages + 1):
            raw = await self.fetch_raw_posts(tags=tags, limit=per_page, page=page)
            if not raw:
                break
            for p in raw:
                post_id = p.get("id")
                if not post_id or post_id in seen_ids:
                    continue
                seen_ids.add(post_id)
                post_tags = p.get("tags", "")
                short_tags = "_".join(post_tags.split()[:4])
                title = f"yande.re_{post_id}_{short_tags}" if short_tags else f"yande.re_{post_id}"
                ext = f".{p.get('file_ext', 'jpg')}"
                all_items.append(
                    ExtractedMediaItem(
                        url=p["file_url"],
                        media_type=MediaType.IMAGE,
                        ext=ext,
                        title=title,
                        headers={"Referer": f"{self.base_url}/post/show/{post_id}"},
                    )
                )
            if len(raw) < per_page:
                break

        endpoint = f"{self.base_url}/post.json?tags={quote_plus(tags.strip())}"
        return ExtractedPageMedia(
            source_url=endpoint,
            platform="Yande.re",
            title=f"Booru Всі: {tags} ({len(all_items)} шт.)",
            description=f"Повний експорт за тегом: {tags}",
            author="yande.re",
            items=all_items,
        )

    async def fetch_posts(
        self,
        tags: str,
        limit: int = 10,
        page: int = 1,
    ) -> ExtractedPageMedia:
        """Повертає пости у вигляді ExtractedPageMedia для завантажувача."""
        raw_posts = await self.fetch_raw_posts(tags=tags, limit=limit, page=page)
        items: list[ExtractedMediaItem] = []
        for p in raw_posts:
            post_id = p.get("id")
            post_tags = p.get("tags", "")
            short_tags = "_".join(post_tags.split()[:4])
            title = f"yande.re_{post_id}_{short_tags}" if short_tags else f"yande.re_{post_id}"
            ext = f".{p.get('file_ext', 'jpg')}"
            items.append(
                ExtractedMediaItem(
                    url=p["file_url"],
                    media_type=MediaType.IMAGE,
                    ext=ext,
                    title=title,
                    headers={"Referer": f"{self.base_url}/post/show/{post_id}"},
                )
            )

        endpoint = f"{self.base_url}/post.json?tags={quote_plus(tags.strip())}&limit={limit}&page={page}"
        return ExtractedPageMedia(
            source_url=endpoint,
            platform="Yande.re",
            title=f"Booru: {tags} ({len(items)} шт.)",
            description=f"Теги пошуку: {tags}",
            author="yande.re",
            items=items,
        )

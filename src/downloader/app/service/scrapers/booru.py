import html
import logging
import re
import time
from typing import Any
from urllib.parse import parse_qs, quote, quote_plus, urlparse
import xml.etree.ElementTree as ET
import aiohttp

from downloader.app.config.constants import DEFAULT_HTTP_HEADERS
from downloader.app.core.dto.media import ExtractedMediaItem, ExtractedPageMedia, MediaType
from downloader.app.service.scrapers.base import BaseScraper

logger = logging.getLogger("downloader.booru")

DEFAULT_BOORU_TAG_SUGGESTIONS: list[dict[str, Any]] = [
    {"name": "order:score", "count": 999999, "type": -1, "type_label": "Сортування"},
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

ZEROCHAN_USER_AGENT = "DownloaderApp - AntiGravityUser"


class BooruService(BaseScraper):
    """
    Універсальний мульти-провайдерний сервіс Booru:
    - Yande.re (Moebooru)
    - Konachan (Moebooru)
    - Safebooru (Gelbooru)
    - Zerochan (Zerochan RSS/API)
    - Gelbooru
    Підтримує пошук за тегами, автодоповнення, Safe Mode (перемикання безпечного режиму з кастомними тегами)
    та пакетне завантаження з високою швидкодією через Persistent Session та Keep-Alive пул з'єднань.
    """

    def __init__(self, base_url: str = "https://yande.re"):
        self.base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None
        self._posts_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._count_cache: dict[str, tuple[float, int]] = {}
        self._tags_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Повертає або ініціалізує оптимізовану сесію з пулом постійних з'єднань (Keep-Alive)."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=20,
                keepalive_timeout=60,
                enable_cleanup_closed=True,
            )
            timeout = aiohttp.ClientTimeout(total=8, connect=4)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers=dict(DEFAULT_HTTP_HEADERS),
            )
        return self._session

    async def close(self) -> None:
        """Закриває активну сесію клієнта при завершенні роботи додатку."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _normalize_provider(self, provider: str | None) -> str:
        p = (provider or "yande.re").strip().lower()
        if "yande" in p:
            return "yande.re"
        if "kona" in p:
            return "konachan"
        if "safe" in p:
            return "safebooru"
        if "zero" in p:
            return "zerochan"
        if "gel" in p:
            return "gelbooru"
        return "yande.re"

    def _get_provider_display_name(self, provider: str) -> str:
        names = {
            "yande.re": "Yande.re",
            "konachan": "Konachan",
            "safebooru": "Safebooru",
            "zerochan": "Zerochan",
            "gelbooru": "Gelbooru",
        }
        return names.get(provider, "Booru")

    def _get_nsfw_filter_sets(
        self,
        safe_tags: str | None = None,
        non_safe_tags: str | None = None,
    ) -> tuple[set[str], set[str], dict[str, list[str]]]:
        """
        Завантажує список NSFW-тегів та рейтингів із nsfw_tags.json (через AccountManager),
        а також враховує кастомні теги, передані користувачем.
        Повертає (nsfw_tags_set, nsfw_ratings_set, query_exclusions_by_provider).
        """
        from downloader.app.core.accounts import account_manager

        cfg = account_manager.get_nsfw_config()
        nsfw_tags_set = set(account_manager.get_nsfw_tags_list())
        nsfw_ratings_set = {str(r).strip().lower() for r in cfg.get("nsfw_ratings", ["explicit", "questionable", "e", "q"])}
        query_exclusions = cfg.get("nsfw_query_exclusions", {})

        # Якщо користувач передав додаткові теги для виключення в Safe Mode або через non_safe_tags
        for extra_raw in (safe_tags, non_safe_tags):
            if extra_raw and extra_raw.strip():
                for part in extra_raw.replace(",", " ").split():
                    clean = part.strip().lower().lstrip("-")
                    if clean:
                        nsfw_tags_set.add(clean)

        return nsfw_tags_set, nsfw_ratings_set, query_exclusions

    def _build_effective_tags(
        self,
        provider: str,
        tags: str,
        safe_mode: bool = False,
        safe_tags: str | None = None,
        non_safe_tags: str | None = None,
    ) -> str:
        """
        Формує підсумковий рядок пошукових тегів.
        Коли увімкнено Safe Mode (safe_mode=True) — виключає небезпечний контент безпосередньо у запиті до API сервера Booru
        відповідно до nsfw_tags.json (напр. rating:safe або -rating:explicit -rating:questionable).
        """
        raw_parts = [t.strip() for t in tags.strip().split() if t.strip()]
        lower_parts = [t.lower() for t in raw_parts]

        if safe_mode:
            _, _, query_exclusions = self._get_nsfw_filter_sets(safe_tags=safe_tags, non_safe_tags=non_safe_tags)
            prov_exclusions = query_exclusions.get(provider, [])
            for exc_tag in prov_exclusions:
                if exc_tag.lower() not in lower_parts:
                    raw_parts.append(exc_tag)
                    lower_parts.append(exc_tag.lower())

            # Для Yande.re, Konachan та Gelbooru додаємо нативний рейтинг фільтрації напряму у запит до сервера
            if provider in ("yande.re", "konachan") and not any(t.startswith("rating:") or t.startswith("-rating:") for t in lower_parts):
                raw_parts.append("rating:safe")
            elif provider == "gelbooru" and not any(t.startswith("rating:") or t.startswith("-rating:") for t in lower_parts):
                raw_parts.append("rating:general")

        return " ".join(raw_parts)

    def _filter_posts_by_nsfw_json(
        self,
        posts: list[dict[str, Any]],
        safe_mode: bool = False,
        safe_tags: str | None = None,
        non_safe_tags: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Строга пост-фільтрація: якщо увімкнено Safe Mode (safe_mode=True),
        відсіває всі пости, які містять будь-який тег або рейтинг із nsfw_tags.json.
        """
        if not safe_mode or not posts:
            return posts

        nsfw_tags_set, nsfw_ratings_set, _ = self._get_nsfw_filter_sets(safe_tags=safe_tags, non_safe_tags=non_safe_tags)
        filtered: list[dict[str, Any]] = []
        for p in posts:
            rating = str(p.get("rating") or "").strip().lower()
            if rating in nsfw_ratings_set or f"rating:{rating}" in nsfw_tags_set:
                continue

            post_tags_raw = str(p.get("tags") or "").lower()
            post_tag_tokens = {t.strip() for t in re.split(r"[\s,]+", post_tags_raw) if t.strip()}
            if post_tag_tokens & nsfw_tags_set:
                continue

            filtered.append(p)
        return filtered

    async def extract(self, url: str) -> ExtractedPageMedia | None:
        """Підтримує прямі посилання на Yande.re, Konachan, Safebooru та Zerochan."""
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()

        # 1. Yande.re
        if "yande.re" in host:
            path = parsed.path.rstrip("/")
            if "/post/show/" in path:
                post_id = path.split("/post/show/")[-1].split("/")[0]
                if post_id.isdigit():
                    return await self.fetch_posts(provider="yande.re", tags=f"id:{post_id}", limit=1)
            query_params = parse_qs(parsed.query)
            if "tags" in query_params and query_params["tags"]:
                return await self.fetch_posts(provider="yande.re", tags=query_params["tags"][0], limit=10)

        # 2. Konachan
        if "konachan" in host:
            path = parsed.path.rstrip("/")
            if "/post/show/" in path:
                post_id = path.split("/post/show/")[-1].split("/")[0]
                if post_id.isdigit():
                    return await self.fetch_posts(provider="konachan", tags=f"id:{post_id}", limit=1)
            query_params = parse_qs(parsed.query)
            if "tags" in query_params and query_params["tags"]:
                return await self.fetch_posts(provider="konachan", tags=query_params["tags"][0], limit=10)

        # 3. Safebooru
        if "safebooru.org" in host:
            query_params = parse_qs(parsed.query)
            if "id" in query_params and query_params["id"]:
                post_id = query_params["id"][0]
                if post_id.isdigit():
                    return await self.fetch_posts(provider="safebooru", tags=f"id:{post_id}", limit=1)
            if "tags" in query_params and query_params["tags"]:
                return await self.fetch_posts(provider="safebooru", tags=query_params["tags"][0], limit=10)

        # 4. Zerochan
        if "zerochan.net" in host:
            path = parsed.path.strip("/")
            if path.isdigit():
                return await self.fetch_posts(provider="zerochan", tags=path, limit=1)
            if path:
                return await self.fetch_posts(provider="zerochan", tags=path, limit=10)

        # 5. Gelbooru
        if "gelbooru.com" in host:
            query_params = parse_qs(parsed.query)
            if "id" in query_params and query_params["id"]:
                post_id = query_params["id"][0]
                if post_id.isdigit():
                    return await self.fetch_posts(provider="gelbooru", tags=f"id:{post_id}", limit=1)
            if "tags" in query_params and query_params["tags"]:
                return await self.fetch_posts(provider="gelbooru", tags=query_params["tags"][0], limit=10)

        return None

    async def search_tags(
        self,
        provider: str = "yande.re",
        query: str = "",
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        """Повертає список підказок тегів для автодоповнення для обраного провайдера."""
        prov = self._normalize_provider(provider)
        q = query.strip().lower().lstrip("#")
        limit = max(1, min(limit, 30))

        if not q:
            return DEFAULT_BOORU_TAG_SUGGESTIONS[:limit]

        cache_key = f"{prov}:{q}:{limit}"
        now = time.time()
        if cache_key in self._tags_cache:
            ts, cached_tags = self._tags_cache[cache_key]
            if now - ts < 300:
                return cached_tags

        results: list[dict[str, Any]] = []
        seen_names: set[str] = set()

        # Спочатку перевіряємо базові мета-теги
        for item in DEFAULT_BOORU_TAG_SUGGESTIONS:
            name = item["name"].lower()
            if name.startswith(q) or q in name:
                results.append(item)
                seen_names.add(name)

        try:
            session = await self._get_session()

            # 1. Yande.re & Konachan (Moebooru)
            if prov in ("yande.re", "konachan"):
                base = "https://yande.re" if prov == "yande.re" else "https://konachan.com"
                endpoint = f"{base}/tag.json?name={quote_plus(q)}&order=count&limit=40"
                headers = {"Referer": f"{base}/"}
                async with session.get(endpoint, headers=headers) as resp:
                    if resp.status == 200:
                        raw_tags: list[dict[str, Any]] = await resp.json()
                        if isinstance(raw_tags, list):
                            for t in raw_tags:
                                t_name = str(t.get("name") or "").strip()
                                if not t_name or t_name.lower() in seen_names:
                                    continue
                                t_type = int(t.get("type", 0))
                                results.append({
                                    "name": t_name,
                                    "count": int(t.get("count", 0)),
                                    "type": t_type,
                                    "type_label": TAG_TYPE_LABELS.get(t_type, "Загальний"),
                                })
                                seen_names.add(t_name.lower())
                                if len(results) >= limit:
                                    break

            # 2. Safebooru autocomplete
            elif prov == "safebooru":
                endpoint = f"https://safebooru.org/autocomplete.php?q={quote_plus(q)}"
                headers = {"Referer": "https://safebooru.org/"}
                async with session.get(endpoint, headers=headers) as resp:
                    if resp.status == 200:
                        items: list[dict[str, str]] = await resp.json()
                        for item in items:
                            val = str(item.get("value") or "").strip()
                            lbl = str(item.get("label") or "")
                            if not val or val.lower() in seen_names:
                                continue
                            count_match = re.search(r"\((\d+)\)", lbl)
                            count = int(count_match.group(1)) if count_match else 0
                            results.append({
                                "name": val,
                                "count": count,
                                "type": 0,
                                "type_label": "Тег",
                            })
                            seen_names.add(val.lower())
                            if len(results) >= limit:
                                break

            # 3. Zerochan suggest
            elif prov == "zerochan":
                endpoint = f"https://www.zerochan.net/suggest?q={quote_plus(q)}"
                headers = {
                    "User-Agent": ZEROCHAN_USER_AGENT,
                    "Referer": "https://www.zerochan.net/",
                }
                async with session.get(endpoint, headers=headers) as resp:
                    if resp.status == 200:
                        raw_text = await resp.text()
                        for line in raw_text.splitlines():
                            parts = line.split("|")
                            if not parts:
                                continue
                            t_name = parts[0].strip()
                            if not t_name or t_name.lower() in seen_names:
                                continue
                            cat_label = parts[1].strip() if len(parts) > 1 else "Тег"
                            results.append({
                                "name": t_name,
                                "count": 0,
                                "type": 0,
                                "type_label": cat_label or "Тег",
                            })
                            seen_names.add(t_name.lower())
                            if len(results) >= limit:
                                break

            # 4. Gelbooru autocomplete
            elif prov == "gelbooru":
                endpoint = f"https://gelbooru.com/index.php?page=autocomplete2&term={quote_plus(q)}&type=tag_query"
                headers = {"Referer": "https://gelbooru.com/"}
                async with session.get(endpoint, headers=headers) as resp:
                    if resp.status == 200:
                        items = await resp.json()
                        if isinstance(items, list):
                            for item in items:
                                val = str(item.get("value") or item.get("label") or "").strip()
                                if not val or val.lower() in seen_names:
                                    continue
                                p_count = int(item.get("post_count") or 0)
                                cat = str(item.get("category") or "tag")
                                results.append({
                                    "name": val,
                                    "count": p_count,
                                    "type": 0,
                                    "type_label": cat.capitalize() or "Тег",
                                })
                                seen_names.add(val.lower())
                                if len(results) >= limit:
                                    break
        except Exception as exc:
            logger.debug("Помилка отримання підказок тегів для %s: %s", prov, exc)

        res = results[:limit]
        self._tags_cache[cache_key] = (now, res)
        return res

    async def search_multi_tags(
        self,
        providers: list[str],
        query: str = "",
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        """Отримує унікальні підказки тегів із кількох провайдерів одночасно."""
        import asyncio
        valid_provs = []
        for p in providers:
            norm = self._normalize_provider(p)
            if norm and norm not in valid_provs:
                valid_provs.append(norm)

        if not valid_provs:
            valid_provs = ["yande.re"]

        if len(valid_provs) == 1:
            return await self.search_tags(provider=valid_provs[0], query=query, limit=limit)

        cache_key = f"multi_tag:{','.join(valid_provs)}:{query}:{limit}"
        now = time.time()
        if cache_key in self._tags_cache:
            ts, val = self._tags_cache[cache_key]
            if now - ts < 300:
                return val

        tasks = [self.search_tags(provider=p, query=query, limit=limit) for p in valid_provs]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        for resp in responses:
            if isinstance(resp, list):
                for item in resp:
                    name = str(item.get("name") or "").lower()
                    if name and name not in seen:
                        seen.add(name)
                        merged.append(item)
                        if len(merged) >= limit:
                            break
            if len(merged) >= limit:
                break

        res = merged[:limit]
        self._tags_cache[cache_key] = (now, res)
        return res

    async def fetch_raw_posts(
        self,
        provider: str = "yande.re",
        tags: str = "",
        limit: int = 24,
        page: int = 1,
        safe_mode: bool = False,
        safe_tags: str | None = None,
        non_safe_tags: str | None = None,
    ) -> list[dict[str, Any]]:
        """Отримує нормалізований список постів для клієнтського браузера."""
        prov = self._normalize_provider(provider)
        limit = max(1, min(limit, 100))
        page = max(1, page)
        eff_tags = self._build_effective_tags(prov, tags, safe_mode=safe_mode, safe_tags=safe_tags, non_safe_tags=non_safe_tags)

        cache_key = f"{prov}:{eff_tags}:{limit}:{page}:{safe_mode}"
        now = time.time()
        if cache_key in self._posts_cache:
            ts, cached_posts = self._posts_cache[cache_key]
            if now - ts < 120:
                return cached_posts

        # Запитуємо з запасом (в 1.5x разів більше) при Safe Mode, щоб гарантувати повну сторінку якісних результатів
        request_limit = min(100, int(limit * 1.5)) if safe_mode else limit
        session = await self._get_session()

        # ----------------------------------------------------
        # 1. Yande.re (Moebooru)
        # ----------------------------------------------------
        if prov == "yande.re":
            encoded_tags = quote_plus(eff_tags.strip())
            endpoint = f"https://yande.re/post.json?tags={encoded_tags}&limit={request_limit}&page={page}"
            headers = {"Referer": "https://yande.re/"}
            try:
                async with session.get(endpoint, headers=headers) as resp:
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
                                "provider": "yande.re",
                                "provider_name": "Yande.re",
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
                                "post_url": f"https://yande.re/post/show/{post_id}",
                                "source": p.get("source", ""),
                            })
                        res = self._filter_posts_by_nsfw_json(cleaned, safe_mode=safe_mode, safe_tags=safe_tags, non_safe_tags=non_safe_tags)
                        self._posts_cache[cache_key] = (now, res)
                        return res
            except Exception as exc:
                logger.error("Помилка отримання постів з Yande.re: %s", exc)
            return []

        # ----------------------------------------------------
        # 2. Konachan (Moebooru)
        # ----------------------------------------------------
        if prov == "konachan":
            base = "https://konachan.net" if safe_mode else "https://konachan.com"
            encoded_tags = quote_plus(eff_tags.strip())
            endpoint = f"{base}/post.json?tags={encoded_tags}&limit={request_limit}&page={page}"
            headers = {"Referer": f"{base}/"}
            try:
                async with session.get(endpoint, headers=headers) as resp:
                    if resp.status == 200:
                        posts = await resp.json()
                        cleaned = []
                        for p in posts:
                            orig_url = p.get("file_url") or p.get("jpeg_url") or p.get("sample_url")
                            if not orig_url:
                                continue
                            post_id = p.get("id")
                            cleaned.append({
                                "id": post_id,
                                "provider": "konachan",
                                "provider_name": "Konachan",
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
                                "post_url": f"{base}/post/show/{post_id}",
                                "source": p.get("source", ""),
                            })
                        res = self._filter_posts_by_nsfw_json(cleaned, safe_mode=safe_mode, safe_tags=safe_tags, non_safe_tags=non_safe_tags)
                        self._posts_cache[cache_key] = (now, res)
                        return res
            except Exception as exc:
                logger.error("Помилка отримання постів з Konachan: %s", exc)
            return []

        # ----------------------------------------------------
        # 3. Safebooru (Gelbooru)
        # ----------------------------------------------------
        if prov == "safebooru":
            pid = max(0, page - 1)
            encoded_tags = quote_plus(eff_tags.strip())
            endpoint = f"https://safebooru.org/index.php?page=dapi&s=post&q=index&json=1&limit={request_limit}&pid={pid}&tags={encoded_tags}"
            headers = {"Referer": "https://safebooru.org/"}
            try:
                async with session.get(endpoint, headers=headers) as resp:
                    if resp.status == 200:
                        posts = await resp.json()
                        cleaned = []
                        if isinstance(posts, list):
                            for p in posts:
                                post_id = p.get("id")
                                directory = p.get("directory")
                                image = p.get("image")
                                orig_url = p.get("file_url") or f"https://safebooru.org/images/{directory}/{image}"
                                preview_url = p.get("preview_url") or f"https://safebooru.org/thumbnails/{directory}/thumbnail_{image}"
                                sample_url = p.get("sample_url") or orig_url
                                ext = image.split(".")[-1] if image and "." in image else "jpg"
                                clean_tags = html.unescape(p.get("tags") or "")
                                cleaned.append({
                                    "id": post_id,
                                    "provider": "safebooru",
                                    "provider_name": "Safebooru",
                                    "tags": clean_tags,
                                    "rating": "safe",
                                    "score": p.get("score", 0),
                                    "width": p.get("width", 0),
                                    "height": p.get("height", 0),
                                    "file_size": 0,
                                    "file_ext": ext,
                                    "preview_url": preview_url,
                                    "sample_url": sample_url,
                                    "file_url": orig_url,
                                    "post_url": f"https://safebooru.org/index.php?page=post&s=view&id={post_id}",
                                    "source": p.get("source", ""),
                                })
                        res = self._filter_posts_by_nsfw_json(cleaned, safe_mode=safe_mode, safe_tags=safe_tags, non_safe_tags=non_safe_tags)
                        self._posts_cache[cache_key] = (now, res)
                        return res
            except Exception as exc:
                logger.error("Помилка отримання постів з Safebooru: %s", exc)
            return []

        # ----------------------------------------------------
        # 4. Zerochan (RSS XML)
        # ----------------------------------------------------
        if prov == "zerochan":
            first_tag = eff_tags.strip().split()[0] if eff_tags.strip() else ""
            if first_tag:
                endpoint = f"https://www.zerochan.net/{quote(first_tag)}?xml&p={page}&l={request_limit}"
            else:
                endpoint = f"https://www.zerochan.net/?xml&p={page}&l={request_limit}"

            headers = {
                "User-Agent": ZEROCHAN_USER_AGENT,
                "Referer": "https://www.zerochan.net/",
            }
            try:
                async with session.get(endpoint, headers=headers) as resp:
                    if resp.status == 200:
                        xml_bytes = await resp.read()
                        root = ET.fromstring(xml_bytes)
                        channel = root.find("channel")
                        items = channel.findall("item") if channel is not None else []
                        cleaned = []
                        media_ns = {"media": "http://search.yahoo.com/mrss/"}

                        for item in items:
                            link = item.findtext("link") or ""
                            post_id = link.rstrip("/").split("/")[-1] if link else "0"
                            title = item.findtext("title") or f"Zerochan #{post_id}"
                            thumb_el = item.find("media:thumbnail", media_ns)
                            content_el = item.find("media:content", media_ns)
                            keywords_el = item.find("media:keywords", media_ns)

                            prev_url = thumb_el.get("url") if thumb_el is not None else ""
                            sample_url = content_el.get("url") if content_el is not None else ""
                            w = int(content_el.get("width", 0)) if content_el is not None else 0
                            h = int(content_el.get("height", 0)) if content_el is not None else 0
                            tags_str = keywords_el.text.strip() if keywords_el is not None and keywords_el.text else title

                            # Full-res URL: static.zerochan.net
                            safe_t = re.sub(r"[^a-zA-Z0-9_\-\.]+", ".", title.strip()).strip(".")
                            full_url = f"https://static.zerochan.net/{safe_t}.full.{post_id}.jpg" if safe_t else sample_url

                            cleaned.append({
                                "id": post_id,
                                "provider": "zerochan",
                                "provider_name": "Zerochan",
                                "tags": tags_str,
                                "rating": "safe",
                                "score": 0,
                                "width": w,
                                "height": h,
                                "file_size": 0,
                                "file_ext": "jpg",
                                "preview_url": prev_url or sample_url,
                                "sample_url": sample_url,
                                "file_url": sample_url or full_url,
                                "post_url": f"https://www.zerochan.net/{post_id}",
                                "source": link,
                            })
                        res = self._filter_posts_by_nsfw_json(cleaned, safe_mode=safe_mode, safe_tags=safe_tags, non_safe_tags=non_safe_tags)
                        self._posts_cache[cache_key] = (now, res)
                        return res
            except Exception as exc:
                logger.error("Помилка отримання постів з Zerochan: %s", exc)
            return []

        # ----------------------------------------------------
        # 5. Gelbooru (HTML scrape + DAPI with API key)
        # ----------------------------------------------------
        if prov == "gelbooru":
            from downloader.app.config.settings import get_settings
            from downloader.app.core.accounts import account_manager

            cur_acc = account_manager.get_current_account()
            api_key = cur_acc.api_keys.gelbooru_api_key if cur_acc and cur_acc.api_keys else None
            user_id = cur_acc.api_keys.gelbooru_user_id if cur_acc and cur_acc.api_keys else None
            if not api_key or not user_id:
                app_settings = get_settings()
                api_key = app_settings.GELBOORU_API_KEY.get_secret_value() if hasattr(app_settings, "GELBOORU_API_KEY") and app_settings.GELBOORU_API_KEY else None
                user_id = app_settings.GELBOORU_USER_ID if hasattr(app_settings, "GELBOORU_USER_ID") and app_settings.GELBOORU_USER_ID else None

            pid = max(0, page - 1)
            encoded_tags = quote_plus(eff_tags.strip())

            # 5a. Спроба через DAPI, якщо налаштовано API-ключ
            if api_key and user_id:
                endpoint = f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&limit={request_limit}&pid={pid}&tags={encoded_tags}&api_key={api_key}&user_id={user_id}"
                headers = {"Referer": "https://gelbooru.com/"}
                try:
                    async with session.get(endpoint, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            posts = data.get("post", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                            cleaned = []
                            for p in posts:
                                post_id = p.get("id")
                                file_url = p.get("file_url")
                                if not file_url:
                                    continue
                                preview_url = p.get("preview_url") or file_url
                                sample_url = p.get("sample_url") or file_url
                                cleaned.append({
                                    "id": post_id,
                                    "provider": "gelbooru",
                                    "provider_name": "Gelbooru",
                                    "tags": html.unescape(p.get("tags") or ""),
                                    "rating": p.get("rating", "general"),
                                    "score": p.get("score", 0),
                                    "width": p.get("width", 0),
                                    "height": p.get("height", 0),
                                    "file_size": 0,
                                    "file_ext": Path(file_url).suffix.lower().lstrip(".") or "jpg",
                                    "preview_url": preview_url,
                                    "sample_url": sample_url,
                                    "file_url": file_url,
                                    "post_url": f"https://gelbooru.com/index.php?page=post&s=view&id={post_id}",
                                    "source": p.get("source", ""),
                                })
                            if cleaned:
                                res = self._filter_posts_by_nsfw_json(cleaned, safe_mode=safe_mode, safe_tags=safe_tags, non_safe_tags=non_safe_tags)
                                self._posts_cache[cache_key] = (now, res)
                                return res
                except Exception as exc:
                    logger.debug("DAPI Gelbooru помилка: %s, перемикаємося на публічний парсер", exc)

            # 5b. Публічний парсер через сторінку списку постів
            list_endpoint = f"https://gelbooru.com/index.php?page=post&s=list&tags={encoded_tags}&pid={pid * limit}"
            headers = {"Referer": "https://gelbooru.com/"}
            try:
                async with session.get(list_endpoint, headers=headers) as resp:
                    if resp.status == 200:
                        page_html = await resp.text()
                        articles = re.findall(r'<article class="thumbnail-preview"[^>]*>(.*?)</article>', page_html, re.DOTALL)
                        cleaned = []
                        for art in articles:
                            m_id = re.search(r'id=["\']p(\d+)["\']', art)
                            m_img = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', art)
                            m_title = re.search(r'title=["\']([^"\']*)["\']', art)
                            if not m_id or not m_img:
                                continue
                            post_id = m_id.group(1)
                            thumb_url = m_img.group(1)
                            title_text = html.unescape(m_title.group(1) if m_title else "")

                            score_m = re.search(r'score:(-?\d+)', title_text)
                            rating_m = re.search(r'rating:([a-zA-Z]+)', title_text)
                            score = int(score_m.group(1)) if score_m else 0
                            rating = rating_m.group(1) if rating_m else "general"

                            clean_tags = re.sub(r'(?:score:-?\d+|rating:[a-zA-Z]+)', '', title_text).strip()
                            preview_url = thumb_url
                            sample_url = thumb_url.replace("/thumbnails/", "/samples/").replace("thumbnail_", "sample_")
                            file_url = sample_url

                            cleaned.append({
                                "id": post_id,
                                "provider": "gelbooru",
                                "provider_name": "Gelbooru",
                                "tags": clean_tags,
                                "rating": rating,
                                "score": score,
                                "width": 0,
                                "height": 0,
                                "file_size": 0,
                                "file_ext": "jpg",
                                "preview_url": preview_url,
                                "sample_url": sample_url,
                                "file_url": file_url,
                                "post_url": f"https://gelbooru.com/index.php?page=post&s=view&id={post_id}",
                                "source": "",
                            })
                            if len(cleaned) >= request_limit:
                                break
                        res = self._filter_posts_by_nsfw_json(cleaned, safe_mode=safe_mode, safe_tags=safe_tags, non_safe_tags=non_safe_tags)
                        self._posts_cache[cache_key] = (now, res)
                        return res
            except Exception as exc:
                logger.error("Помилка публічного парсера Gelbooru: %s", exc)
            return []

        return []

    async def fetch_multi_raw_posts(
        self,
        providers: list[str],
        tags: str = "",
        limit: int = 24,
        page: int = 1,
        safe_mode: bool = False,
        safe_tags: str | None = None,
        non_safe_tags: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Одночасний пошук за тегами на кількох Booru-серверах (паралельно)
        зі швидким пріоритетом (fast-first) та збалансованим об'єднанням результатів (Round-Robin).
        """
        import asyncio
        valid_provs: list[str] = []
        for p in providers:
            norm = self._normalize_provider(p)
            if norm and norm not in valid_provs:
                valid_provs.append(norm)

        if not valid_provs:
            valid_provs = ["yande.re"]

        if len(valid_provs) == 1:
            return await self.fetch_raw_posts(
                provider=valid_provs[0],
                tags=tags,
                limit=limit,
                page=page,
                safe_mode=safe_mode,
                safe_tags=safe_tags,
                non_safe_tags=non_safe_tags,
            )

        cache_key = f"multi_posts:{','.join(valid_provs)}:{tags}:{limit}:{page}:{safe_mode}"
        now = time.time()
        if cache_key in self._posts_cache:
            ts, val = self._posts_cache[cache_key]
            if now - ts < 60:
                return val

        per_provider_limit = max(8, limit)
        tasks = {
            asyncio.create_task(
                self.fetch_raw_posts(
                    provider=prov,
                    tags=tags,
                    limit=per_provider_limit,
                    page=page,
                    safe_mode=safe_mode,
                    safe_tags=safe_tags,
                    non_safe_tags=non_safe_tags,
                )
            ): prov
            for prov in valid_provs
        }

        # Очікуємо швидкі відповіді до 650мс
        done, pending = await asyncio.wait(tasks.keys(), timeout=0.65)

        results_lists: list[list[dict[str, Any]]] = []
        for t in done:
            try:
                resp = t.result()
                if isinstance(resp, list) and resp:
                    results_lists.append(resp)
            except Exception as exc:
                logger.warning("Помилка запиту до одного з провайдерів Booru: %s", exc)

        total_fast_posts = sum(len(l) for l in results_lists)

        # Якщо швидких постів недостатньо і є очікуючі запити (наприклад, повільний Gelbooru), дочекаємося їх
        if total_fast_posts < limit and pending:
            done_more, _ = await asyncio.wait(pending, timeout=1.5)
            for t in done_more:
                try:
                    resp = t.result()
                    if isinstance(resp, list) and resp:
                        results_lists.append(resp)
                except Exception as exc:
                    logger.warning("Помилка запиту до одного з провайдерів Booru: %s", exc)

        if not results_lists:
            return []

        merged: list[dict[str, Any]] = []
        max_len = max((len(l) for l in results_lists), default=0)
        seen_ids: set[str] = set()

        for i in range(max_len):
            for l in results_lists:
                if i < len(l):
                    item = l[i]
                    unique_key = f"{item.get('provider')}_{item.get('id')}"
                    if unique_key not in seen_ids:
                        seen_ids.add(unique_key)
                        merged.append(item)
                        if len(merged) >= limit:
                            break
            if len(merged) >= limit:
                break

        res = merged[:limit]
        self._posts_cache[cache_key] = (now, res)
        return res

    async def get_posts_count(
        self,
        provider: str = "yande.re",
        tags: str = "",
        safe_mode: bool = False,
        safe_tags: str | None = None,
        non_safe_tags: str | None = None,
    ) -> int:
        """Отримує точну або оціночну загальну кількість постів за тегами (або всього на сервері)."""
        prov = self._normalize_provider(provider)
        eff_tags = self._build_effective_tags(prov, tags, safe_mode=safe_mode, safe_tags=safe_tags, non_safe_tags=non_safe_tags)
        cache_key = f"cnt:{prov}:{eff_tags}:{safe_mode}"
        now = time.time()
        if cache_key in self._count_cache:
            ts, val = self._count_cache[cache_key]
            if now - ts < 180:
                return val

        encoded_tags = quote_plus(eff_tags.strip())

        try:
            session = await self._get_session()

            # 1. Yande.re
            if prov == "yande.re":
                url = f"https://yande.re/post.xml?limit=0&tags={encoded_tags}"
                headers = {"Referer": "https://yande.re/"}
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        xml_bytes = await resp.read()
                        root = ET.fromstring(xml_bytes)
                        cnt = root.attrib.get("count")
                        if cnt and cnt.isdigit():
                            res = int(cnt)
                            self._count_cache[cache_key] = (now, res)
                            return res

            # 2. Konachan
            elif prov == "konachan":
                base = "https://konachan.net" if safe_mode else "https://konachan.com"
                url = f"{base}/post.xml?limit=0&tags={encoded_tags}"
                headers = {"Referer": f"{base}/"}
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        xml_bytes = await resp.read()
                        root = ET.fromstring(xml_bytes)
                        cnt = root.attrib.get("count")
                        if cnt and cnt.isdigit():
                            res = int(cnt)
                            self._count_cache[cache_key] = (now, res)
                            return res

            # 3. Safebooru
            elif prov == "safebooru":
                url = f"https://safebooru.org/index.php?page=dapi&s=post&q=index&limit=0&tags={encoded_tags}"
                headers = {"Referer": "https://safebooru.org/"}
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        xml_bytes = await resp.read()
                        root = ET.fromstring(xml_bytes)
                        cnt = root.attrib.get("count")
                        if cnt and cnt.isdigit():
                            res = int(cnt)
                            self._count_cache[cache_key] = (now, res)
                            return res

            # 4. Gelbooru
            elif prov == "gelbooru":
                from downloader.app.config.settings import get_settings
                from downloader.app.core.accounts import account_manager

                cur_acc = account_manager.get_current_account()
                api_key = cur_acc.api_keys.gelbooru_api_key if cur_acc and cur_acc.api_keys else None
                user_id = cur_acc.api_keys.gelbooru_user_id if cur_acc and cur_acc.api_keys else None
                if not api_key or not user_id:
                    app_settings = get_settings()
                    api_key = app_settings.GELBOORU_API_KEY.get_secret_value() if hasattr(app_settings, "GELBOORU_API_KEY") and app_settings.GELBOORU_API_KEY else None
                    user_id = app_settings.GELBOORU_USER_ID if hasattr(app_settings, "GELBOORU_USER_ID") and app_settings.GELBOORU_USER_ID else None

                headers = {"Referer": "https://gelbooru.com/"}

                # Якщо є API-ключ, миттєво отримуємо точний count через DAPI XML
                if api_key and user_id:
                    dapi_url = f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&limit=0&tags={encoded_tags}&api_key={api_key}&user_id={user_id}"
                    try:
                        async with session.get(dapi_url, headers=headers) as resp:
                            if resp.status == 200:
                                xml_bytes = await resp.read()
                                root = ET.fromstring(xml_bytes)
                                cnt = root.attrib.get("count")
                                if cnt and cnt.isdigit():
                                    res = int(cnt)
                                    self._count_cache[cache_key] = (now, res)
                                    return res
                    except Exception as exc:
                        logger.debug("DAPI Gelbooru count error: %s", exc)

                # Публічний список
                url = f"https://gelbooru.com/index.php?page=post&s=list&tags={encoded_tags}"
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        html_text = await resp.text()
                        m = re.findall(r'pid=(\d+)[^>]*alt=[\"\']last page[\"\']', html_text)
                        if m and m[0].isdigit():
                            res = int(m[0]) + 42
                            self._count_cache[cache_key] = (now, res)
                            return res
                        posts_count = len(re.findall(r'<article class="thumbnail-preview"', html_text))
                        self._count_cache[cache_key] = (now, posts_count)
                        return posts_count

            # 5. Zerochan
            elif prov == "zerochan":
                first_tag = eff_tags.strip().split()[0] if eff_tags.strip() else ""
                url = f"https://www.zerochan.net/{quote(first_tag)}?p=1" if first_tag else "https://www.zerochan.net/?p=1"
                headers = {
                    "User-Agent": ZEROCHAN_USER_AGENT,
                    "Referer": "https://www.zerochan.net/",
                }
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        html_text = await resp.text()
                        m = re.search(r'page\s+\d+\s+of\s+([0-9,]+)', html_text, re.I)
                        if m:
                            pages_str = m.group(1).replace(",", "")
                            if pages_str.isdigit():
                                res = int(pages_str) * 24
                                self._count_cache[cache_key] = (now, res)
                                return res
        except Exception as exc:
            logger.debug("Не вдалося отримати точну кількість постів для %s: %s", prov, exc)

        return 0

    async def get_multi_posts_count(
        self,
        providers: list[str],
        tags: str = "",
        safe_mode: bool = False,
        safe_tags: str | None = None,
        non_safe_tags: str | None = None,
    ) -> int:
        """Отримує сумарну кількість постів для списку серверів."""
        import asyncio
        valid_provs = []
        for p in providers:
            norm = self._normalize_provider(p)
            if norm and norm not in valid_provs:
                valid_provs.append(norm)

        if not valid_provs:
            valid_provs = ["yande.re"]

        cache_key = f"multi_cnt:{','.join(valid_provs)}:{tags}:{safe_mode}"
        now = time.time()
        if cache_key in self._count_cache:
            ts, val = self._count_cache[cache_key]
            if now - ts < 180:
                return val

        tasks = [
            self.get_posts_count(
                provider=p,
                tags=tags,
                safe_mode=safe_mode,
                safe_tags=safe_tags,
                non_safe_tags=non_safe_tags,
            )
            for p in valid_provs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total = 0
        for r in results:
            if isinstance(r, int) and r > 0:
                total += r

        self._count_cache[cache_key] = (now, total)
        return total

    async def fetch_posts(
        self,
        provider: str = "yande.re",
        tags: str = "",
        limit: int = 10,
        page: int = 1,
        safe_mode: bool = False,
        safe_tags: str | None = None,
        non_safe_tags: str | None = None,
    ) -> ExtractedPageMedia:
        """Повертає пости у вигляді ExtractedPageMedia для завантажувача."""
        prov = self._normalize_provider(provider)
        plat_name = self._get_provider_display_name(prov)
        raw_posts = await self.fetch_raw_posts(
            provider=prov,
            tags=tags,
            limit=limit,
            page=page,
            safe_mode=safe_mode,
            safe_tags=safe_tags,
            non_safe_tags=non_safe_tags,
        )

        items: list[ExtractedMediaItem] = []
        for p in raw_posts:
            post_id = p.get("id")
            post_tags = p.get("tags", "")
            short_tags = "_".join(post_tags.split()[:4])
            prefix = prov.replace(".", "_")
            title = f"{prefix}_{post_id}_{short_tags}" if short_tags else f"{prefix}_{post_id}"
            ext = f".{p.get('file_ext', 'jpg')}"

            # Заголовки Referer для завантаження
            ref = p.get("post_url") or f"https://{prov}/"
            headers = {"Referer": ref}
            if prov == "zerochan":
                headers["User-Agent"] = ZEROCHAN_USER_AGENT

            items.append(
                ExtractedMediaItem(
                    url=p["file_url"],
                    media_type=MediaType.IMAGE,
                    ext=ext,
                    title=title,
                    headers=headers,
                )
            )

        return ExtractedPageMedia(
            source_url=f"booru:{prov}:{tags}",
            platform=plat_name,
            title=f"{plat_name}: {tags} ({len(items)} шт.)",
            description=f"Теги пошуку: {tags}",
            author=prov,
            items=items,
        )

    async def fetch_all_posts_by_tag(
        self,
        provider: str = "yande.re",
        tags: str = "",
        max_pages: int = 10,
        per_page: int = 100,
        safe_mode: bool = False,
        safe_tags: str | None = None,
        non_safe_tags: str | None = None,
    ) -> ExtractedPageMedia:
        """Посторінково витягує всі доступні пости за тегом до вичерпання або max_pages."""
        prov = self._normalize_provider(provider)
        plat_name = self._get_provider_display_name(prov)
        all_items: list[ExtractedMediaItem] = []
        seen_ids: set[Any] = set()

        for page in range(1, max_pages + 1):
            raw = await self.fetch_raw_posts(
                provider=prov,
                tags=tags,
                limit=per_page,
                page=page,
                safe_mode=safe_mode,
                safe_tags=safe_tags,
                non_safe_tags=non_safe_tags,
            )
            if not raw:
                break
            for p in raw:
                post_id = p.get("id")
                if not post_id or post_id in seen_ids:
                    continue
                seen_ids.add(post_id)
                post_tags = p.get("tags", "")
                short_tags = "_".join(post_tags.split()[:4])
                prefix = prov.replace(".", "_")
                title = f"{prefix}_{post_id}_{short_tags}" if short_tags else f"{prefix}_{post_id}"
                ext = f".{p.get('file_ext', 'jpg')}"

                ref = p.get("post_url") or f"https://{prov}/"
                headers = {"Referer": ref}
                if prov == "zerochan":
                    headers["User-Agent"] = ZEROCHAN_USER_AGENT

                all_items.append(
                    ExtractedMediaItem(
                        url=p["file_url"],
                        media_type=MediaType.IMAGE,
                        ext=ext,
                        title=title,
                        headers=headers,
                    )
                )
            if len(raw) < per_page:
                break

        return ExtractedPageMedia(
            source_url=f"booru:{prov}:{tags}",
            platform=plat_name,
            title=f"{plat_name} Всі: {tags} ({len(all_items)} шт.)",
            description=f"Повний експорт за тегом: {tags}",
            author=prov,
            items=all_items,
        )

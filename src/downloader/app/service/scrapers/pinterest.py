import html
import re
from urllib.parse import urlparse
import aiohttp

from downloader.app.config.constants import DEFAULT_HTTP_HEADERS
from downloader.app.core.dto.media import ExtractedMediaItem, ExtractedPageMedia, MediaType
from downloader.app.service.scrapers.base import BaseScraper

PINTEREST_PIN_RE = re.compile(r"/pin/(?:[^/?#]*--)?(\d+)", re.IGNORECASE)
PINIMG_HASH_RE = re.compile(
    r"https://i\.pinimg\.com/(?:originals|\d+x(?:/\w+)?)/([a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]+)\.(jpg|jpeg|png|webp|gif)",
    re.IGNORECASE,
)


class PinterestScraper(BaseScraper):
    """Ізольований скрапер для Pinterest (піни, короткі посилання pin.it, оригінали зображень та GIF)."""

    def can_handle(self, url: str) -> bool:
        host = (urlparse(url).netloc or "").lower()
        return "pinterest." in host or "pin.it" in host or "pinimg.com" in host

    async def _resolve_redirects(self, session: aiohttp.ClientSession, url: str) -> str:
        try:
            async with session.get(url, allow_redirects=True) as resp:
                final_url = str(resp.url)
                # Якщо редірект привів на проміжну сторінку з параметром url=...
                if "/url_shortener/" in final_url or "pin/" not in final_url:
                    text = await resp.text(errors="ignore")
                    pin_url_match = re.search(
                        r"https?://(?:[\w-]+\.)?pinterest\.[a-z.]+/pin/(?:[^/?#\"'\s]*--)?\d+/?",
                        text,
                        re.IGNORECASE,
                    )
                    if pin_url_match:
                        return pin_url_match.group(0)
                return final_url
        except Exception:
            return url

    async def _resolve_best_original_for_hash(
        self,
        session: aiohttp.ClientSession,
        hash_path: str,
        default_ext: str,
        page_html: str = "",
        fallback_url: str = "",
    ) -> str:
        """
        Знаходить або перевіряє наявність максимальної якості (/originals/) саме для хешу поточного піна,
        ігноруючи сторонні іконки інтерфейсу Pinterest або рекомендовані піни.
        """
        # 1. Шукаємо точний збіг /originals/<hash_path>.<ext> у тексті сторінки
        if page_html:
            pattern = re.compile(
                rf"https://i\.pinimg\.com/originals/{re.escape(hash_path)}\.(?:jpg|jpeg|png|gif|webp)",
                re.IGNORECASE,
            )
            m = pattern.search(page_html)
            if m:
                return m.group(0)

        # 2. Перевіряємо можливі розширення в /originals/ через швидкий Range-запит
        exts_to_try = [default_ext.lower().lstrip(".")]
        for cand_ext in ("jpg", "png", "gif", "webp", "jpeg"):
            if cand_ext not in exts_to_try:
                exts_to_try.append(cand_ext)

        for ext in exts_to_try:
            cand_url = f"https://i.pinimg.com/originals/{hash_path}.{ext}"
            try:
                async with session.get(
                    cand_url,
                    headers={"Range": "bytes=0-64", "Referer": "https://www.pinterest.com/"},
                ) as resp:
                    if resp.status in (200, 206):
                        return cand_url
            except Exception:
                continue

        # 3. Якщо /originals/ недоступний — повертаємо 736x для цього ж хешу
        url_736 = f"https://i.pinimg.com/736x/{hash_path}.jpg"
        try:
            async with session.get(
                url_736,
                headers={"Range": "bytes=0-64", "Referer": "https://www.pinterest.com/"},
            ) as resp:
                if resp.status in (200, 206):
                    return url_736
        except Exception:
            pass

        return fallback_url or url_736

    async def extract(self, url: str) -> ExtractedPageMedia | None:
        timeout = aiohttp.ClientTimeout(total=18, connect=10)
        headers = {
            **DEFAULT_HTTP_HEADERS,
            "Referer": "https://www.pinterest.com/",
        }

        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            resolved_url = await self._resolve_redirects(session, url)
            pin_match = PINTEREST_PIN_RE.search(resolved_url)
            pin_id = pin_match.group(1) if pin_match else None

            page_html = ""
            try:
                async with session.get(resolved_url) as resp:
                    if resp.status == 200:
                        page_html = await resp.text(errors="ignore")
            except Exception:
                pass

            # 1. Офіційний Pinterest Pidgets API для точного pin_id
            if pin_id:
                try:
                    api_url = f"https://api.pinterest.com/v3/pidgets/pins/info/?pin_ids={pin_id}"
                    async with session.get(api_url) as resp:
                        if resp.status == 200:
                            payload = await resp.json()
                            pins = (payload.get("data") or {}).get("pins") or []
                            if pins:
                                pin = pins[0]
                                raw_desc = (
                                    pin.get("description")
                                    or (pin.get("rich_metadata") or {}).get("title")
                                    or ""
                                ).strip()
                                title = raw_desc[:100] if raw_desc else f"Pinterest Pin {pin_id}"

                                # Якщо це анімований GIF, Pidgets часто віддає прямий оригінал у embed.src
                                embed = pin.get("embed") or {}
                                embed_src = embed.get("src")
                                if embed_src and "i.pinimg.com" in embed_src:
                                    hm = PINIMG_HASH_RE.search(embed_src)
                                    if hm:
                                        best_url = await self._resolve_best_original_for_hash(
                                            session,
                                            hash_path=hm.group(1),
                                            default_ext=hm.group(2),
                                            page_html=page_html,
                                            fallback_url=embed_src,
                                        )
                                    else:
                                        best_url = embed_src

                                    return ExtractedPageMedia(
                                        source_url=url,
                                        platform="Pinterest",
                                        title=title,
                                        description=raw_desc or title,
                                        items=[
                                            ExtractedMediaItem(
                                                url=best_url,
                                                media_type=MediaType.IMAGE,
                                                title=title[:80],
                                            )
                                        ],
                                    )

                                images = pin.get("images") or {}
                                img_url = None
                                for key in ("orig", "736x", "564x", "237x"):
                                    if key in images and isinstance(images[key], dict) and images[key].get("url"):
                                        img_url = images[key]["url"]
                                        break

                                if img_url:
                                    hm = PINIMG_HASH_RE.search(img_url)
                                    if hm:
                                        best_url = await self._resolve_best_original_for_hash(
                                            session,
                                            hash_path=hm.group(1),
                                            default_ext=hm.group(2),
                                            page_html=page_html,
                                            fallback_url=img_url,
                                        )
                                    else:
                                        best_url = img_url

                                    return ExtractedPageMedia(
                                        source_url=url,
                                        platform="Pinterest",
                                        title=title,
                                        description=raw_desc or title,
                                        items=[
                                            ExtractedMediaItem(
                                                url=best_url,
                                                media_type=MediaType.IMAGE,
                                                title=title[:80],
                                            )
                                        ],
                                    )
                except Exception:
                    pass

            # 2. Парсинг головних мета-тегів сторінки (preload as="image" та og:image)
            if page_html:
                og_title = (
                    re.search(
                        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
                        page_html,
                        re.IGNORECASE,
                    )
                    or re.search(
                        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
                        page_html,
                        re.IGNORECASE,
                    )
                )
                title = html.unescape(og_title.group(1)).strip() if og_title else f"Pinterest {pin_id or 'Pin'}"
                if not title or title.lower() == "pinterest":
                    title = f"Pinterest {pin_id or 'Pin'}"

                primary_patterns = [
                    r'<link[^>]+rel=["\']preload["\'][^>]+as=["\']image["\'][^>]+href=["\'](https://i\.pinimg\.com/[^"\']+)["\']',
                    r'<link[^>]+href=["\'](https://i\.pinimg\.com/[^"\']+)["\'][^>]+rel=["\']preload["\'][^>]+as=["\']image["\']',
                    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https://i\.pinimg\.com/[^"\']+)["\']',
                    r'<meta[^>]+content=["\'](https://i\.pinimg\.com/[^"\']+)["\'][^>]+property=["\']og:image["\']',
                    r'<meta[^>]+name=["\']twitter:image:src["\'][^>]+content=["\'](https://i\.pinimg\.com/[^"\']+)["\']',
                    r'<meta[^>]+content=["\'](https://i\.pinimg\.com/[^"\']+)["\'][^>]+name=["\']twitter:image:src["\']',
                ]

                primary_candidates: list[str] = []
                for pat in primary_patterns:
                    for m in re.finditer(pat, page_html, re.IGNORECASE):
                        cand = html.unescape(m.group(1))
                        if cand not in primary_candidates:
                            primary_candidates.append(cand)

                for cand in primary_candidates:
                    hm = PINIMG_HASH_RE.search(cand)
                    if hm:
                        best_url = await self._resolve_best_original_for_hash(
                            session,
                            hash_path=hm.group(1),
                            default_ext=hm.group(2),
                            page_html=page_html,
                            fallback_url=cand,
                        )
                        return ExtractedPageMedia(
                            source_url=url,
                            platform="Pinterest",
                            title=title[:100],
                            items=[
                                ExtractedMediaItem(
                                    url=best_url,
                                    media_type=MediaType.IMAGE,
                                    title=title[:80],
                                )
                            ],
                        )

        return None


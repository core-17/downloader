import html
from urllib.parse import urlparse
import aiohttp

from downloader.app.config.constants import DEFAULT_HTTP_HEADERS, IMAGE_EXTENSIONS
from downloader.app.core.dto.media import ExtractedMediaItem, ExtractedPageMedia, MediaType
from downloader.app.service.scrapers.base import BaseScraper


class RedditScraper(BaseScraper):
    """Ізольований скрапер для постів та галерей Reddit."""

    def can_handle(self, url: str) -> bool:
        host = (urlparse(url).netloc or "").lower()
        return ("reddit.com" in host or "redd.it" in host) and "v.redd.it" not in host

    async def _resolve_redirects(self, session: aiohttp.ClientSession, url: str) -> str:
        try:
            async with session.get(url, allow_redirects=True) as resp:
                return str(resp.url)
        except Exception:
            return url

    async def extract(self, url: str) -> ExtractedPageMedia | None:
        timeout = aiohttp.ClientTimeout(total=15)
        headers = {
            **DEFAULT_HTTP_HEADERS,
            "User-Agent": "Mozilla/5.0 (compatible; UniversalMediaDownloader/0.1; +https://reddit.com)",
        }
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            resolved_url = await self._resolve_redirects(session, url)
            parsed = urlparse(resolved_url)
            clean_path = parsed.path.rstrip("/")
            if not clean_path.endswith(".json"):
                json_url = f"https://www.reddit.com{clean_path}.json?raw_json=1"
            else:
                json_url = f"https://www.reddit.com{clean_path}?raw_json=1"

            try:
                async with session.get(json_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list) and data:
                            children = (data[0].get("data") or {}).get("children") or []
                            if children:
                                post = children[0].get("data") or {}
                                title = post.get("title") or "Reddit Post"
                                author = post.get("author")
                                items: list[ExtractedMediaItem] = []

                                # 1. Галерея Reddit (кілька зображень)
                                if post.get("is_gallery") and post.get("media_metadata"):
                                    meta = post["media_metadata"]
                                    gallery_items = (post.get("gallery_data") or {}).get("items") or []
                                    media_ids = [g.get("media_id") for g in gallery_items if g.get("media_id")]
                                    if not media_ids:
                                        media_ids = list(meta.keys())

                                    for mid in media_ids:
                                        m_info = meta.get(mid) or {}
                                        s_info = m_info.get("s") or {}
                                        img_url = s_info.get("u") or s_info.get("gif") or s_info.get("mp4")
                                        if img_url:
                                            items.append(
                                                ExtractedMediaItem(
                                                    url=html.unescape(img_url),
                                                    media_type=MediaType.IMAGE,
                                                    title=title[:80],
                                                )
                                            )

                                # 2. Пряме посилання на зображення в пості (i.redd.it, i.imgur.com)
                                dest_url = post.get("url_overridden_by_dest") or post.get("url")
                                if not items and dest_url:
                                    dest_ext = urlparse(dest_url).path.lower()
                                    if any(dest_ext.endswith(ext) for ext in IMAGE_EXTENSIONS):
                                        items.append(
                                            ExtractedMediaItem(
                                                url=html.unescape(dest_url),
                                                media_type=MediaType.IMAGE,
                                                title=title[:80],
                                            )
                                        )

                                # 3. Preview image fallback
                                if not items:
                                    previews = (post.get("preview") or {}).get("images") or []
                                    if previews:
                                        src_url = (previews[0].get("source") or {}).get("url")
                                        if src_url and not post.get("is_video"):
                                            items.append(
                                                ExtractedMediaItem(
                                                    url=html.unescape(src_url),
                                                    media_type=MediaType.IMAGE,
                                                    title=title[:80],
                                                )
                                            )

                                if items:
                                    return ExtractedPageMedia(
                                        source_url=url,
                                        platform="Reddit",
                                        title=title[:120],
                                        author=author,
                                        items=items,
                                    )
            except Exception:
                pass

        return None


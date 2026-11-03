import html
from html.parser import HTMLParser
import json
from urllib.parse import urljoin, urlparse
import aiohttp

from downloader.app.config.constants import DEFAULT_HTTP_HEADERS, VIDEO_EXTENSIONS
from downloader.app.core.dto.media import ExtractedMediaItem, ExtractedPageMedia, MediaType
from downloader.app.service.scrapers.base import BaseScraper

IGNORED_IMAGE_PATTERNS = (
    "logo",
    "icon",
    "favicon",
    "avatar",
    "sprite",
    "pixel",
    "tracker",
    "1x1",
    "blank.gif",
    "spacer",
    "badge",
    "emoji",
)


class _MediaHTMLParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.in_title = False
        self.in_ld_json = False
        self.title_parts: list[str] = []
        self.ld_json_blocks: list[str] = []
        self.og_title: str | None = None
        self.og_description: str | None = None
        self.meta_images: list[str] = []
        self.meta_videos: list[str] = []
        self.body_images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = {k.lower(): (v or "").strip() for k, v in attrs if k}

        if tag == "title":
            self.in_title = True

        elif tag == "script" and attr_map.get("type", "").lower() == "application/ld+json":
            self.in_ld_json = True

        elif tag == "meta":
            prop = (attr_map.get("property") or attr_map.get("name") or attr_map.get("itemprop") or "").lower()
            content = attr_map.get("content") or ""
            if not content:
                return
            if prop in ("og:title", "twitter:title") and not self.og_title:
                self.og_title = html.unescape(content)
            elif prop in ("og:description", "twitter:description", "description") and not self.og_description:
                self.og_description = html.unescape(content)
            elif prop in (
                "og:image",
                "og:image:secure_url",
                "og:image:url",
                "twitter:image",
                "twitter:image:src",
                "image",
            ):
                full_url = urljoin(self.base_url, html.unescape(content))
                if full_url.startswith("http") and full_url not in self.meta_images:
                    self.meta_images.append(full_url)
            elif prop in ("og:video", "og:video:secure_url", "og:video:url", "twitter:player:stream"):
                full_url = urljoin(self.base_url, html.unescape(content))
                if full_url.startswith("http") and full_url not in self.meta_videos:
                    self.meta_videos.append(full_url)

        elif tag == "link":
            rel = attr_map.get("rel", "").lower()
            href = attr_map.get("href", "")
            if rel == "image_src" and href:
                full_url = urljoin(self.base_url, html.unescape(href))
                if full_url.startswith("http") and full_url not in self.meta_images:
                    self.meta_images.append(full_url)

        elif tag == "img":
            src = (
                attr_map.get("data-original")
                or attr_map.get("data-src")
                or attr_map.get("data-lazy-src")
                or attr_map.get("src")
                or ""
            )
            srcset = attr_map.get("srcset") or attr_map.get("data-srcset") or ""
            if srcset:
                # Обираємо останній (найбільший) елемент із srcset
                parts = [p.strip().split()[0] for p in srcset.split(",") if p.strip()]
                if parts:
                    src = parts[-1]

            if not src or src.startswith("data:"):
                return

            width = attr_map.get("width", "")
            height = attr_map.get("height", "")
            if (width.isdigit() and int(width) < 120) or (height.isdigit() and int(height) < 120):
                return

            full_url = urljoin(self.base_url, html.unescape(src))
            lower_url = full_url.lower()
            if any(pat in lower_url for pat in IGNORED_IMAGE_PATTERNS):
                return
            if lower_url.endswith(".svg"):
                return
            if full_url.startswith("http") and full_url not in self.body_images:
                self.body_images.append(full_url)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self.in_title = False
        elif tag == "script" and self.in_ld_json:
            self.in_ld_json = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        elif self.in_ld_json:
            self.ld_json_blocks.append(data)


class StaticWebScraper(BaseScraper):
    """Екстрактор зображень та медіа зі звичайних веб-сайтів (OpenGraph, JSON-LD, головні <img>)."""

    async def extract(self, url: str) -> ExtractedPageMedia | None:
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(headers=DEFAULT_HTTP_HEADERS, timeout=timeout) as session:
                async with session.get(url, allow_redirects=True) as resp:
                    if resp.status >= 400:
                        return None
                    final_url = str(resp.url)
                    ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()

                    if ctype.startswith("image/"):
                        return ExtractedPageMedia(
                            source_url=url,
                            platform=urlparse(final_url).netloc or "web",
                            title=urlparse(final_url).path.split("/")[-1] or "Image",
                            items=[ExtractedMediaItem(url=final_url, media_type=MediaType.IMAGE)],
                        )

                    if "html" not in ctype:
                        return None

                    raw_html = await resp.text(errors="ignore")
        except Exception:
            return None

        parser = _MediaHTMLParser(base_url=final_url)
        try:
            parser.feed(raw_html)
        except Exception:
            pass

        # Перевіряємо JSON-LD на наявність image / contentUrl
        for block in parser.ld_json_blocks:
            try:
                ld_data = json.loads(block)
                self._extract_ld_images(ld_data, final_url, parser.meta_images)
            except Exception:
                pass

        title = parser.og_title or "".join(parser.title_parts).strip() or urlparse(final_url).netloc
        items: list[ExtractedMediaItem] = []

        # Спочатку прямі відео з meta, якщо вони мають розширення відеофайлу
        for v_url in parser.meta_videos:
            v_path = urlparse(v_url).path.lower()
            if any(v_path.endswith(ext) for ext in VIDEO_EXTENSIONS):
                items.append(ExtractedMediaItem(url=v_url, media_type=MediaType.VIDEO, title=title[:80]))

        # Далі головні зображення з OpenGraph / Twitter Card / JSON-LD
        for img_url in parser.meta_images:
            items.append(ExtractedMediaItem(url=img_url, media_type=MediaType.IMAGE, title=title[:80]))

        # Якщо meta-зображень немає — беремо перші значущі зображення з тіла сторінки (до 5 шт)
        if not items and parser.body_images:
            for img_url in parser.body_images[:5]:
                items.append(ExtractedMediaItem(url=img_url, media_type=MediaType.IMAGE, title=title[:80]))

        if not items:
            return None

        return ExtractedPageMedia(
            source_url=url,
            platform=urlparse(final_url).netloc or "web",
            title=title[:120],
            description=parser.og_description,
            items=items,
        )

    def _extract_ld_images(self, obj: object, base_url: str, target: list[str]) -> None:
        if isinstance(obj, dict):
            for key in ("image", "contentUrl", "thumbnailUrl"):
                val = obj.get(key)
                if isinstance(val, str) and val.startswith(("http://", "https://", "/")):
                    full = urljoin(base_url, val)
                    if full not in target:
                        target.append(full)
                elif isinstance(val, (dict, list)):
                    self._extract_ld_images(val, base_url, target)
            if "@graph" in obj:
                self._extract_ld_images(obj["@graph"], base_url, target)
        elif isinstance(obj, list):
            for elem in obj:
                self._extract_ld_images(elem, base_url, target)


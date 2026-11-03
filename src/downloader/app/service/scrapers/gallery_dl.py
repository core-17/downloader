import asyncio
import json
import shutil

from downloader.app.config.constants import VIDEO_EXTENSIONS
from downloader.app.core.dto.media import ExtractedMediaItem, ExtractedPageMedia, MediaType
from downloader.app.service.scrapers.base import BaseScraper


class GalleryDlScraper(BaseScraper):
    """Ізольований адаптер для зовнішньої CLI-утиліти gallery-dl (якщо встановлена у системі)."""

    def can_handle(self, url: str) -> bool:
        return bool(shutil.which("gallery-dl"))

    async def extract(self, url: str) -> ExtractedPageMedia | None:
        if not self.can_handle(url):
            return None
        try:
            proc = await asyncio.create_subprocess_exec(
                "gallery-dl",
                "--dump-json",
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
            if proc.returncode != 0 or not stdout:
                return None
            data = json.loads(stdout.decode("utf-8", errors="ignore"))
            items: list[ExtractedMediaItem] = []
            title = None
            for entry in data:
                if isinstance(entry, list) and len(entry) >= 2:
                    item_url = entry[1] if isinstance(entry[1], str) else None
                    meta = entry[-1] if isinstance(entry[-1], dict) else {}
                    if not title and meta.get("title"):
                        title = str(meta.get("title"))
                    if item_url and item_url.startswith("http"):
                        ext = f".{meta['extension']}" if meta.get("extension") else None
                        mtype = (
                            MediaType.VIDEO
                            if ext and ext.lower() in VIDEO_EXTENSIONS
                            else MediaType.IMAGE
                        )
                        items.append(ExtractedMediaItem(url=item_url, media_type=mtype, ext=ext))
            if items:
                return ExtractedPageMedia(
                    source_url=url,
                    platform="Gallery",
                    title=title or "Gallery Media",
                    items=items,
                )
        except Exception:
            return None
        return None


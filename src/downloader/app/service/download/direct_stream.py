import asyncio
import mimetypes
from pathlib import Path
import time
from urllib.parse import unquote, urlparse
import aiofiles
import aiohttp

from downloader.app.config.constants import (
    AUDIO_EXTENSIONS,
    DEFAULT_HTTP_HEADERS,
    DOCUMENT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    MIME_TO_EXT,
    VIDEO_EXTENSIONS,
)
from downloader.app.core.dto.media import ExtractedMediaItem, MediaType
from downloader.app.core.dto.task import TaskProgress, TaskStatus
from downloader.app.service.download.base import (
    BaseDownloader,
    ProgressCallback,
    sanitize_filename,
)


def _build_referer_headers(url: str, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    headers = dict(DEFAULT_HTTP_HEADERS)
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if "pinimg.com" in host or "pinterest." in host:
        headers["Referer"] = "https://www.pinterest.com/"
    elif "twimg.com" in host or "twitter.com" in host or "x.com" in host:
        headers["Referer"] = "https://x.com/"
    elif "redd.it" in host or "reddit.com" in host:
        headers["Referer"] = "https://www.reddit.com/"
    elif "imgur.com" in host:
        headers["Referer"] = "https://imgur.com/"
    else:
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

    if extra_headers:
        headers.update(extra_headers)
    return headers


def _guess_extension_and_type(url: str, content_type: str | None) -> tuple[str, str]:
    mime = (content_type or "").split(";")[0].strip().lower()
    parsed_path = unquote(urlparse(url).path)
    url_ext = Path(parsed_path).suffix.lower()

    # Перевіряємо відомий розширення з URL (наприклад .jpg, .png, .mp4)
    all_known = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS | DOCUMENT_EXTENSIONS
    ext = url_ext if url_ext in all_known else ""

    if not ext and mime in MIME_TO_EXT:
        ext = MIME_TO_EXT[mime]
    if not ext and mime:
        guessed = mimetypes.guess_extension(mime)
        if guessed:
            ext = guessed.lower()
    if not ext:
        # Для Twitter pbs.twimg.com/media/XYZ?format=jpg&name=large
        query = urlparse(url).query.lower()
        for fmt in ("jpg", "jpeg", "png", "webp", "gif", "mp4"):
            if f"format={fmt}" in query:
                ext = f".{fmt}" if fmt != "jpeg" else ".jpg"
                break
    if not ext:
        ext = ".jpg" if mime.startswith("image/") else ".bin"

    if ext in IMAGE_EXTENSIONS or mime.startswith("image/"):
        mtype = "image"
    elif ext in VIDEO_EXTENSIONS or mime.startswith("video/"):
        mtype = "video"
    elif ext in AUDIO_EXTENSIONS or mime.startswith("audio/"):
        mtype = "audio"
    else:
        mtype = "document"
    return ext, mtype


class DirectStreamDownloader(BaseDownloader):
    """Завантажувач прямих посилань на картинки, медіафайли, документи та списки зображень (галереї)."""

    def __init__(self, temp_dir: Path, max_concurrent: int = 4):
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def probe_url(self, url: str) -> tuple[bool, str | None, str]:
        """
        Перевіряє, чи посилання вказує напряму на медіа/бінарний файл (не HTML-сторінку).
        Повертає (is_direct_media, content_type, final_url).
        """
        headers = _build_referer_headers(url)
        timeout = aiohttp.ClientTimeout(total=12)
        try:
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url, allow_redirects=True) as resp:
                    if resp.status >= 400:
                        return False, None, str(resp.url)
                    ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                    final_url = str(resp.url)
                    if ctype.startswith(("image/", "video/", "audio/")) or ctype in (
                        "application/pdf",
                        "application/epub+zip",
                        "application/zip",
                        "application/octet-stream",
                    ):
                        return True, ctype, final_url
                    return False, ctype, final_url
        except Exception:
            return False, None, url

    async def download(
        self,
        task_id: str,
        url: str,
        on_progress: ProgressCallback | None = None,
        title: str | None = None,
        source_platform: str | None = None,
        extra_headers: dict[str, str] | None = None,
        **kwargs,
    ) -> TaskProgress:
        item = ExtractedMediaItem(
            url=url,
            title=title,
            headers=extra_headers or {},
        )
        return await self.download_items(
            task_id=task_id,
            source_url=url,
            items=[item],
            title=title,
            source_platform=source_platform or "direct",
            on_progress=on_progress,
        )

    async def download_items(
        self,
        task_id: str,
        source_url: str,
        items: list[ExtractedMediaItem],
        title: str | None = None,
        description: str | None = None,
        source_platform: str = "web",
        on_progress: ProgressCallback | None = None,
    ) -> TaskProgress:
        progress = TaskProgress(
            task_id=task_id,
            url=source_url,
            title=title,
            description=description,
            source_platform=source_platform,
            status=TaskStatus.DOWNLOADING,
            media_type="gallery" if len(items) > 1 else "image",
        )
        if on_progress:
            await on_progress(progress)

        async with self._semaphore:
            task_dir = self.temp_dir / task_id
            task_dir.mkdir(parents=True, exist_ok=True)
            downloaded_files: list[Path] = []
            total_downloaded_bytes = 0
            last_emit = 0.0

            timeout = aiohttp.ClientTimeout(total=120, connect=15)
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    for idx, item in enumerate(items, start=1):
                        headers = _build_referer_headers(item.url, item.headers)
                        async with session.get(item.url, headers=headers, allow_redirects=True) as resp:
                            resp.raise_for_status()
                            ctype = resp.headers.get("Content-Type")
                            ext, detected_type = _guess_extension_and_type(str(resp.url), ctype)
                            if item.ext and item.ext.startswith("."):
                                ext = item.ext

                            raw_name = item.title or title or Path(unquote(urlparse(str(resp.url)).path)).stem or "media"
                            safe_stem = sanitize_filename(raw_name, max_len=75)
                            filename = f"{safe_stem}{ext}"

                            # 0. Перевірка на дублікат у сховищі (уникнення повторного завантаження ідентичних файлів)
                            from downloader.app.connect.web.state import downloader as app_dispatcher
                            existing_file = await app_dispatcher.storage.find_existing_file_by_name(filename)
                            if existing_file and existing_file.exists() and existing_file.stat().st_size > 0:
                                downloaded_files.append(existing_file)
                                if len(items) == 1:
                                    progress.media_type = detected_type
                                continue

                            file_path = task_dir / filename

                            # Якщо файл з таким ім'ям вже існує (наприклад однакові назви у галереї), робимо унікальним
                            if file_path.exists():
                                file_path = task_dir / f"{safe_stem}_{idx}{ext}"
                            content_len = resp.headers.get("Content-Length")
                            expected_bytes = int(content_len) if content_len and content_len.isdigit() else None
                            if expected_bytes and len(items) == 1:
                                progress.total_mb = round(expected_bytes / (1024 * 1024), 2)

                            item_bytes = 0
                            start_ts = time.monotonic()
                            async with aiofiles.open(file_path, "wb") as f:
                                async for chunk in resp.content.iter_chunked(64 * 1024):
                                    await f.write(chunk)
                                    item_bytes += len(chunk)
                                    total_downloaded_bytes += len(chunk)

                                    now = time.monotonic()
                                    if on_progress and (now - last_emit >= 0.4):
                                        last_emit = now
                                        elapsed = max(0.01, now - start_ts)
                                        progress.downloaded_mb = round(total_downloaded_bytes / (1024 * 1024), 2)
                                        progress.speed_mb_s = round((item_bytes / (1024 * 1024)) / elapsed, 2)
                                        if len(items) == 1 and expected_bytes and expected_bytes > 0:
                                            progress.percent = min(99.9, round((item_bytes / expected_bytes) * 100, 1))
                                        else:
                                            progress.percent = min(99.9, round(((idx - 1) / len(items)) * 100, 1))
                                        await on_progress(progress)

                            if file_path.exists() and file_path.stat().st_size > 0:
                                downloaded_files.append(file_path)
                                if len(items) == 1:
                                    progress.media_type = detected_type

                if not downloaded_files:
                    raise RuntimeError("Не вдалося завантажити жодного файлу за прямим посиланням.")

                progress.file_path = str(downloaded_files[0])
                progress.file_paths = [str(p) for p in downloaded_files]
                if len(downloaded_files) > 1:
                    progress.media_type = "gallery"
                if not progress.title:
                    progress.title = downloaded_files[0].stem
                progress.downloaded_mb = round(total_downloaded_bytes / (1024 * 1024), 2)
                progress.total_mb = progress.downloaded_mb
                progress.percent = 100.0
                progress.status = TaskStatus.COMPLETED
                if on_progress:
                    await on_progress(progress)
                return progress

            except Exception as exc:
                progress.status = TaskStatus.FAILED
                progress.error = str(exc)
                if on_progress:
                    await on_progress(progress)
                return progress


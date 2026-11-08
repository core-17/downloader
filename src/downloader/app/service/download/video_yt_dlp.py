import asyncio
from pathlib import Path
import re
import time
from typing import Any
import yt_dlp

from downloader.app.config.constants import (
    AUDIO_EXTENSIONS,
    DEFAULT_USER_AGENT,
    IMAGE_EXTENSIONS,
)
from downloader.app.core.dto.task import TaskProgress, TaskStatus
from downloader.app.service.download.base import BaseDownloader, ProgressCallback


class YtDlpDownloader(BaseDownloader):
    """Універсальний завантажувач відео/аудіо через yt-dlp (YouTube, X/Twitter, Reddit, Pinterest, TikTok, Instagram тощо)."""

    def __init__(self, temp_dir: Path, max_concurrent: int = 4):
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def download(
        self,
        task_id: str,
        url: str,
        max_height: int = 1080,
        on_progress: ProgressCallback | None = None,
        audio_only: bool = False,
        download_playlist: bool = True,
        **kwargs,
    ) -> TaskProgress:
        progress = TaskProgress(
            task_id=task_id,
            url=url,
            status=TaskStatus.QUEUED,
            media_type="audio" if audio_only else "video",
        )
        if on_progress:
            await on_progress(progress)

        async with self._semaphore:
            loop = asyncio.get_running_loop()
            try:
                progress.status = TaskStatus.EXTRACTING
                if on_progress:
                    await on_progress(progress)

                files, title, description, extractor, files_meta, playlist_title = await asyncio.to_thread(
                    self._sync_download_worker,
                    task_id,
                    url,
                    max_height,
                    audio_only,
                    progress,
                    loop,
                    on_progress,
                    download_playlist,
                )

                if not files:
                    raise RuntimeError("yt-dlp не створив жодного медіафайлу для цього посилання.")

                progress.title = title
                progress.description = description
                progress.source_platform = extractor
                progress.file_path = str(files[0])
                progress.file_paths = [str(f) for f in files]
                progress.files_meta = files_meta

                # Якщо завантажено плейлист, додаємо назву плейлиста до загальних тегів задачі
                if playlist_title:
                    clean_p = re.sub(r"[^\w\s-]", "", playlist_title).strip().lower().replace(" ", "_")
                    clean_p = clean_p[:60]
                    if clean_p and clean_p not in progress.tags:
                        progress.tags.append(clean_p)

                first_ext = files[0].suffix.lower()
                if audio_only or first_ext in AUDIO_EXTENSIONS:
                    progress.media_type = "audio"
                elif first_ext in IMAGE_EXTENSIONS:
                    progress.media_type = "gallery" if len(files) > 1 else "image"
                else:
                    progress.media_type = "video"

                total_bytes = sum(f.stat().st_size for f in files if f.exists())
                if total_bytes > 0:
                    progress.downloaded_mb = round(total_bytes / (1024 * 1024), 2)
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

    def _sync_download_worker(
        self,
        task_id: str,
        url: str,
        max_height: int,
        audio_only: bool,
        progress: TaskProgress,
        loop: asyncio.AbstractEventLoop,
        on_progress: ProgressCallback | None,
        download_playlist: bool = True,
    ) -> tuple[list[Path], str, str | None, str | None, dict[str, Any], str | None]:
        task_dir = self.temp_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        last_emit = 0.0

        def ytdlp_hook(d: dict[str, Any]) -> None:
            nonlocal last_emit
            status = d.get("status")
            info_dict = d.get("info_dict") or {}
            if not progress.title and info_dict.get("title"):
                progress.title = info_dict.get("title")
            if not progress.source_platform and info_dict.get("extractor_key"):
                progress.source_platform = info_dict.get("extractor_key")

            if status == "downloading":
                progress.status = TaskStatus.DOWNLOADING
                downloaded = d.get("downloaded_bytes", 0) or 0
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                speed = d.get("speed")
                p_idx = info_dict.get("playlist_index")
                p_count = info_dict.get("playlist_count") or info_dict.get("n_entries")

                if p_idx and p_count:
                    v_title = info_dict.get("title") or ""
                    progress.description = f"[{p_idx}/{p_count}] {v_title[:55]}"
                    if total and total > 0:
                        v_percent = min(100.0, (downloaded / total) * 100)
                        progress.percent = min(99.9, round(((p_idx - 1) / p_count) * 100 + (v_percent / p_count), 1))
                    else:
                        progress.percent = min(99.9, round(((p_idx - 1) / p_count) * 100, 1))
                else:
                    if total and total > 0:
                        progress.percent = min(99.9, round((downloaded / total) * 100, 1))

                if speed:
                    progress.speed_mb_s = round(speed / (1024 * 1024), 2)
                eta = d.get("eta")
                progress.eta_seconds = int(eta) if isinstance(eta, (int, float)) else None

                now = time.monotonic()
                if on_progress and (now - last_emit >= 0.5):
                    last_emit = now
                    asyncio.run_coroutine_threadsafe(on_progress(progress), loop)

            elif status == "finished":
                progress.status = TaskStatus.PROCESSING
                progress.percent = 99.9
                if on_progress:
                    asyncio.run_coroutine_threadsafe(on_progress(progress), loop)

        outtmpl_pattern = str(task_dir / "%(playlist_index&{:04d} - |)s%(title).80B [%(id)s].%(ext)s")

        if audio_only:
            ydl_opts: dict[str, Any] = {
                "format": "bestaudio/best",
                "outtmpl": outtmpl_pattern,
                "noplaylist": not download_playlist,
                "continuedl": True,
                "nopart": False,
                "progress_hooks": [ytdlp_hook],
                "quiet": True,
                "no_warnings": True,
                "ignoreerrors": True,
                "http_headers": {"User-Agent": DEFAULT_USER_AGENT},
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }
        else:
            if not max_height or max_height <= 0 or max_height >= 4320:
                fmt_selector = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            else:
                fmt_selector = (
                    f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/"
                    f"bestvideo[height<={max_height}]+bestaudio/"
                    f"best[height<={max_height}]/"
                    "best"
                )
            ydl_opts = {
                "format": fmt_selector,
                "outtmpl": outtmpl_pattern,
                "merge_output_format": "mp4",
                "noplaylist": not download_playlist,
                "continuedl": True,
                "nopart": False,
                "progress_hooks": [ytdlp_hook],
                "quiet": True,
                "no_warnings": True,
                "ignoreerrors": True,
                "http_headers": {"User-Agent": DEFAULT_USER_AGENT},
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise RuntimeError("Не вдалося отримати метадані через yt-dlp")

            is_playlist = info.get("_type") == "playlist" or bool(info.get("entries"))
            playlist_title = info.get("title") if is_playlist else (info.get("playlist_title") or None)
            title = playlist_title or info.get("title") or info.get("description") or "Media"
            description = info.get("description")
            extractor = info.get("extractor_key") or info.get("extractor")

            # Збираємо всі завантажені файли у папці задачі, відсортовані за назвою (0001, 0002...)
            downloaded_files = sorted(
                [
                    p
                    for p in task_dir.iterdir()
                    if p.is_file()
                    and not p.name.endswith((".part", ".ytdl", ".temp", ".json"))
                    and p.stat().st_size > 0
                ],
                key=lambda p: p.name,
            )

            if not downloaded_files:
                filename = ydl.prepare_filename(info)
                candidate = Path(filename).with_suffix(".mp3" if audio_only else ".mp4")
                if candidate.exists():
                    downloaded_files = [candidate]
                elif Path(filename).exists():
                    downloaded_files = [Path(filename)]

            # Формуємо метадані для кожного файлу: назва плейлиста та порядковий тег (0001, 0002...)
            files_meta: dict[str, Any] = {}
            clean_playlist_tag = None
            if playlist_title:
                clean_playlist_tag = re.sub(r"[^\w\s-]", "", playlist_title).strip().lower().replace(" ", "_")
                clean_playlist_tag = clean_playlist_tag[:60]

            for idx, file_path in enumerate(downloaded_files, start=1):
                fname = file_path.name
                match = re.match(r"^(\d{4})[-_\s]", fname)
                if match:
                    item_idx_str = match.group(1)
                elif is_playlist or len(downloaded_files) > 1:
                    item_idx_str = f"{idx:04d}"
                else:
                    item_idx_str = None

                item_tags: list[str] = []
                if clean_playlist_tag:
                    item_tags.append(clean_playlist_tag)
                if item_idx_str:
                    item_tags.append(item_idx_str)

                files_meta[fname] = {
                    "tags": item_tags,
                    "playlist_index": int(item_idx_str) if item_idx_str and item_idx_str.isdigit() else idx,
                    "playlist_title": playlist_title,
                }

            return downloaded_files, str(title)[:200], description, extractor, files_meta, playlist_title

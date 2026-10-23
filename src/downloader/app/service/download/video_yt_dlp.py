import asyncio
from pathlib import Path
from typing import Callable, Awaitable, Any
import yt_dlp

from downloader.app.core.dto.task import TaskProgress, TaskStatus

ProgressCallback = Callable[[TaskProgress], Awaitable[None]]


class YtDlpDownloader:
    def __init__(self, temp_dir: Path, max_concurrent: int = 4):
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def download(
        self,
        task_id: str,
        url: str,
        max_height: int,
        on_progress: ProgressCallback,
    ) -> TaskProgress:
        progress = TaskProgress(task_id=task_id, url=url, status=TaskStatus.QUEUED)
        await on_progress(progress)

        async with self._semaphore:
            loop = asyncio.get_running_loop()
            try:
                progress.status = TaskStatus.EXTRACTING
                await on_progress(progress)

                result_path, title = await asyncio.to_thread(
                    self._sync_download_worker,
                    task_id,
                    url,
                    max_height,
                    progress,
                    loop,
                    on_progress,
                )

                progress.title = title
                progress.file_path = str(result_path)
                progress.percent = 100.0
                progress.status = TaskStatus.COMPLETED
                await on_progress(progress)
                return progress

            except Exception as exc:
                progress.status = TaskStatus.FAILED
                progress.error = str(exc)
                await on_progress(progress)
                return progress

    def _sync_download_worker(
        self,
        task_id: str,
        url: str,
        max_height: int,
        progress: TaskProgress,
        loop: asyncio.AbstractEventLoop,
        on_progress: ProgressCallback,
    ) -> tuple[Path, str]:
        task_dir = self.temp_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        def ytdlp_hook(d: dict[str, Any]) -> None:
            status = d.get("status")
            info_dict = d.get("info_dict", {})
            if not progress.title and info_dict.get("title"):
                progress.title = info_dict.get("title")

            if status == "downloading":
                progress.status = TaskStatus.DOWNLOADING
                downloaded = d.get("downloaded_bytes", 0)
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                speed = d.get("speed")

                progress.downloaded_mb = round(downloaded / (1024 * 1024), 2)
                if total:
                    progress.total_mb = round(total / (1024 * 1024), 2)
                    progress.percent = round((downloaded / total) * 100, 1)
                if speed:
                    progress.speed_mb_s = round(speed / (1024 * 1024), 2)
                progress.eta_seconds = d.get("eta")

                asyncio.run_coroutine_threadsafe(on_progress(progress), loop)

            elif status == "finished":
                progress.status = TaskStatus.PROCESSING
                progress.percent = 99.9
                asyncio.run_coroutine_threadsafe(on_progress(progress), loop)

        ydl_opts = {
            "format": f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]/best",
            "outtmpl": str(task_dir / "%(title).100s.%(ext)s"),
            "merge_output_format": "mp4",
            "continuedl": True,
            "nopart": False,
            "progress_hooks": [ytdlp_hook],
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            final_path = Path(filename).with_suffix(".mp4")
            if not final_path.exists():
                final_path = Path(filename)
            return final_path, info.get("title", "Unknown")
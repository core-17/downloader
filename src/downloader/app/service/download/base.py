from abc import ABC, abstractmethod
import re
from typing import Awaitable, Callable

from downloader.app.core.dto.task import TaskProgress

ProgressCallback = Callable[[TaskProgress], Awaitable[None]]


def sanitize_filename(name: str, max_len: int = 80) -> str:
    """Очищує назву файлу від небезпечних символів та обмежує довжину."""
    cleaned = re.sub(r'[\\/*?:"<>|\r\n\t]+', "_", name).strip(" ._")
    if not cleaned:
        cleaned = "media_file"
    # Обмежуємо довжину у символах і байтах (UTF-8 ліміт файлової системи Linux — 255 байт)
    cleaned = cleaned[:max_len]
    while len(cleaned.encode("utf-8")) > 180:
        cleaned = cleaned[:-1]
    return cleaned or "media_file"


class BaseDownloader(ABC):
    @abstractmethod
    async def download(
        self,
        task_id: str,
        url: str,
        on_progress: ProgressCallback | None = None,
        **kwargs,
    ) -> TaskProgress:
        raise NotImplementedError


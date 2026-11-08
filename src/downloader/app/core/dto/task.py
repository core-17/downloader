from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, HttpUrl


class TaskStatus(str, Enum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DownloadRequest(BaseModel):
    url: str = Field(..., description="Посилання на медіа або сторінку (або booru:теги)")
    title: str | None = Field(default=None, description="Бажана назва файлу (опціонально)")
    max_height: int = Field(default=1080, description="Максимальна висота відео (480, 720, 1080, 2160)")
    audio_only: bool = Field(default=False, description="Завантажити лише аудіодоріжку (MP3)")
    tags: list[str] = Field(default_factory=list, description="Теги користувача")
    # Налаштування для обробки зображень
    image_format: str = Field(default="original", description="Формат збереження зображень: original, jpg, png, webp, avif")
    image_max_side: int | None = Field(default=None, description="Максимальний розмір по більшій стороні (пікселів)")
    source_platform: str | None = Field(default=None, description="Платформа-джерело або назва сайту")
    download_playlist: bool = Field(default=True, description="Завантажувати весь плейлист, якщо це посилання на плейлист")


class BooruDownloadRequest(BaseModel):
    tags: str = Field(..., description="Теги для пошуку на Booru (наприклад, 'landscape', 'genshin_impact')")
    limit: int = Field(default=10, description="Кількість зображень для завантаження (1-1000)")
    download_all: bool = Field(default=False, description="Завантажити всі доступні пости за цим тегом (посторінково)")
    max_pages: int = Field(default=10, description="Максимальна кількість сторінок при download_all (за замовчуванням до 10 сторінок)")
    image_format: str = Field(default="original", description="Формат: original, jpg, png, webp, avif")
    image_max_side: int | None = Field(default=None, description="Максимальний розмір по більшій стороні")
    user_tags: list[str] = Field(default_factory=list, description="Додаткові теги користувача для архіву")
    provider: str = Field(default="yande.re", description="Джерело Booru: yande.re, konachan, safebooru, zerochan")
    safe_mode: bool = Field(default=False, description="Безпечний режим (Safe Mode)")
    safe_tags: str | None = Field(default=None, description="Кастомні теги безпечного режиму")
    non_safe_tags: str | None = Field(default=None, description="Кастомні теги звичайного режиму")


class UpdateFileTagsRequest(BaseModel):
    relative_path: str = Field(..., description="Відносний шлях файлу в сховищі")
    tags: list[str] = Field(default_factory=list, description="Оновлений список тегів")


class TaskProgress(BaseModel):
    task_id: str
    url: str
    status: TaskStatus = TaskStatus.QUEUED
    media_type: str = "video"
    source_platform: str | None = None
    title: str | None = None
    description: str | None = None
    percent: float = 0.0
    downloaded_mb: float = 0.0
    total_mb: float | None = None
    speed_mb_s: float = 0.0
    eta_seconds: int | None = None
    file_path: str | None = None
    file_paths: list[str] = Field(default_factory=list)
    files_meta: dict[str, Any] = Field(default_factory=dict, description="Метадані окремих файлів (індекси, теги плейлиста)")
    tags: list[str] = Field(default_factory=list)
    error: str | None = None

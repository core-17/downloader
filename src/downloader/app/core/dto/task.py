from enum import Enum
from pydantic import BaseModel, Field, HttpUrl


class TaskStatus(str, Enum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DownloadRequest(BaseModel):
    url: HttpUrl = Field(..., description="Посилання на медіа")
    max_height: int = Field(default=1080, description="Максимальна висота відео (720, 1080)")


class TaskProgress(BaseModel):
    task_id: str
    url: str
    status: TaskStatus = TaskStatus.QUEUED
    title: str | None = None
    percent: float = 0.0
    downloaded_mb: float = 0.0
    total_mb: float | None = None
    speed_mb_s: float = 0.0
    eta_seconds: int | None = None
    file_path: str | None = None
    error: str | None = None
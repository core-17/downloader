import asyncio
import uuid
from fastapi import APIRouter
from pydantic import BaseModel

from downloader.app.connect.web.state import broadcast_progress, downloader, tasks_state
from downloader.app.core.dto.task import DownloadRequest, TaskProgress

router = APIRouter(tags=["Downloads"])


class BatchDownloadRequest(BaseModel):
    items: list[DownloadRequest]


@router.post("/api/v1/download", response_model=TaskProgress)
async def start_download(req: DownloadRequest) -> TaskProgress:
    task_id = str(uuid.uuid4())[:8]
    initial_progress = TaskProgress(
        task_id=task_id,
        url=str(req.url),
        title=req.title,
        media_type="audio" if req.audio_only else "video",
        tags=req.tags,
    )
    tasks_state[task_id] = initial_progress

    asyncio.create_task(
        downloader.download(
            task_id=task_id,
            url=str(req.url),
            title=req.title,
            max_height=req.max_height,
            audio_only=req.audio_only,
            on_progress=broadcast_progress,
            tags=req.tags,
            image_format=req.image_format,
            image_max_side=req.image_max_side,
        )
    )
    return initial_progress


@router.post("/api/v1/download/batch", response_model=list[TaskProgress])
async def start_batch_download(req: BatchDownloadRequest) -> list[TaskProgress]:
    """Пакетний запуск завантаження декількох посилань одразу."""
    results = []
    for item in req.items:
        res = await start_download(item)
        results.append(res)
    return results


@router.get("/api/v1/tasks", response_model=list[TaskProgress])
async def list_tasks() -> list[TaskProgress]:
    return list(tasks_state.values())


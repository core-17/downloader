import asyncio
from pathlib import Path
from urllib.parse import urlparse
import uuid
import aiohttp
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from downloader.app.config.constants import IMAGE_EXTENSIONS
from downloader.app.connect.web.state import broadcast_progress, downloader, tasks_state
from downloader.app.core.dto.task import BooruDownloadRequest, TaskProgress, TaskStatus
from downloader.app.service.compression.transcoder import process_image

router = APIRouter(tags=["Booru"])


@router.get("/api/v1/booru/posts")
async def get_booru_posts(tags: str = "", limit: int = 24, page: int = 1):
    """Отримання списку постів Yande.re для клієнтської вітрини та нескінченного скролу."""
    return await downloader.booru_service.fetch_raw_posts(tags=tags, limit=limit, page=page)


@router.get("/api/v1/booru/tags")
async def get_booru_tags(q: str = "", limit: int = 12):
    """Автодоповнення та підказки тегів Yande.re при вводі в рядок пошуку."""
    return await downloader.booru_service.search_tags(query=q, limit=limit)


@router.get("/api/v1/booru/proxy")
async def proxy_booru_image(url: str) -> Response:
    """Безпечний проксі-фолбек для відображення зображень Yande.re, якщо CDN блокує прямий хотлінк."""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if not host.endswith("yande.re"):
        raise HTTPException(status_code=400, detail="Дозволено лише домени yande.re")

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Referer": "https://yande.re/",
    }
    timeout = aiohttp.ClientTimeout(total=30, connect=10)
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        async with session.get(url) as resp:
            if resp.status >= 400:
                raise HTTPException(status_code=resp.status, detail="Не вдалося завантажити зображення з Yande.re")
            body = await resp.read()
            ctype = resp.headers.get("Content-Type", "image/jpeg")
            return Response(
                content=body,
                media_type=ctype,
                headers={"Cache-Control": "public, max-age=86400"},
            )


@router.post("/api/v1/booru/download", response_model=TaskProgress)
async def start_booru_download(req: BooruDownloadRequest) -> TaskProgress:
    """Пошук та пакетне завантаження ілюстрацій з Yande.re за вказаними тегами."""
    task_id = str(uuid.uuid4())[:8]
    initial_progress = TaskProgress(
        task_id=task_id,
        url=f"https://yande.re/post?tags={req.tags}",
        title=f"Booru: {req.tags}",
        media_type="gallery",
        source_platform="Yande.re",
        status=TaskStatus.EXTRACTING,
        tags=req.user_tags or [t for t in req.tags.split() if t],
    )
    tasks_state[task_id] = initial_progress
    await broadcast_progress(initial_progress)

    async def _run_booru() -> None:
        if req.download_all:
            page_media = await downloader.booru_service.fetch_all_posts_by_tag(
                tags=req.tags,
                max_pages=req.max_pages or 10,
                per_page=100,
            )
        else:
            page_media = await downloader.booru_service.fetch_posts(tags=req.tags, limit=req.limit)

        if not page_media or not page_media.items:
            initial_progress.status = TaskStatus.FAILED
            initial_progress.error = f"За тегами «{req.tags}» на Yande.re нічого не знайдено."
            await broadcast_progress(initial_progress)
            return

        res = await downloader.direct.download_items(
            task_id=task_id,
            source_url=f"https://yande.re/post?tags={req.tags}",
            items=page_media.items,
            title=page_media.title,
            description=page_media.description,
            source_platform="Yande.re",
            on_progress=broadcast_progress,
        )

        fmt = (req.image_format or "original").lower().strip()
        max_s = req.image_max_side if req.image_max_side and req.image_max_side > 0 else None
        if fmt != "original" or max_s:
            new_paths = []
            for p_str in res.file_paths:
                p = Path(p_str)
                if p.suffix.lower() in IMAGE_EXTENSIONS:
                    processed = await process_image(p, target_format=fmt, max_side=max_s)
                    new_paths.append(str(processed))
                else:
                    new_paths.append(str(p))
            res.file_paths = new_paths
            if new_paths:
                res.file_path = new_paths[0]

        res.tags = req.user_tags or [t for t in req.tags.split() if t]
        await downloader.storage.save_task_metadata(task_id, res)
        await broadcast_progress(res)

    asyncio.create_task(_run_booru())
    return initial_progress


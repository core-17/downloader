import asyncio
from pathlib import Path
from urllib.parse import urlparse
import uuid
import aiohttp
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from downloader.app.config.constants import IMAGE_EXTENSIONS
from downloader.app.connect.web.state import broadcast_progress, downloader, tasks_state
from downloader.app.core.dto.task import BooruDownloadRequest, TaskProgress, TaskStatus
from downloader.app.service.compression.transcoder import process_image

router = APIRouter(tags=["Booru"])


@router.get("/api/v1/booru/posts")
async def get_booru_posts(
    provider: str = "yande.re",
    tags: str = "",
    limit: int = 24,
    page: int = 1,
    safe_mode: bool = False,
    safe_tags: str | None = None,
    non_safe_tags: str | None = None,
):
    """Отримання списку постів Booru (Yande.re, Konachan, Safebooru, Zerochan, Gelbooru) з підтримкою мультивибору та Safe Mode."""
    prov_list = [p.strip() for p in provider.split(",") if p.strip()]
    if not prov_list:
        prov_list = ["yande.re"]
    return await downloader.booru_service.fetch_multi_raw_posts(
        providers=prov_list,
        tags=tags,
        limit=limit,
        page=page,
        safe_mode=safe_mode,
        safe_tags=safe_tags,
        non_safe_tags=non_safe_tags,
    )


@router.get("/api/v1/booru/nsfw-tags")
async def get_nsfw_tags_config():
    """Отримання поточної конфігурації тегів NSFW із nsfw_tags.json."""
    from downloader.app.core.accounts import account_manager
    return account_manager.get_nsfw_config()


class UpdateNsfwTagsPayload(BaseModel):
    tags: list[str]


@router.post("/api/v1/booru/nsfw-tags")
async def update_nsfw_tags_config(payload: UpdateNsfwTagsPayload):
    """Оновлення списку тегів NSFW у nsfw_tags.json."""
    from downloader.app.core.accounts import account_manager
    return account_manager.update_nsfw_tags_list(payload.tags)


@router.get("/api/v1/booru/count")
async def get_booru_count(
    provider: str = "yande.re",
    tags: str = "",
    safe_mode: bool = False,
    safe_tags: str | None = None,
    non_safe_tags: str | None = None,
):
    """Отримання точної/оціночної загальної кількості постів для запиту."""
    prov_list = [p.strip() for p in provider.split(",") if p.strip()]
    if not prov_list:
        prov_list = ["yande.re"]
    total = await downloader.booru_service.get_multi_posts_count(
        providers=prov_list,
        tags=tags,
        safe_mode=safe_mode,
        safe_tags=safe_tags,
        non_safe_tags=non_safe_tags,
    )
    return {"total": total}


@router.get("/api/v1/booru/tags")
async def get_booru_tags(
    provider: str = "yande.re",
    q: str = "",
    limit: int = 12,
):
    """Автодоповнення та підказки тегів для одного або кількох обраних Booru-сервісів."""
    prov_list = [p.strip() for p in provider.split(",") if p.strip()]
    if not prov_list:
        prov_list = ["yande.re"]
    return await downloader.booru_service.search_multi_tags(
        providers=prov_list,
        query=q,
        limit=limit,
    )


@router.get("/api/v1/booru/proxy")
async def proxy_booru_image(url: str) -> Response:
    """Безпечний проксі-фолбек для відображення зображень Booru (якщо CDN блокує хотлінк)."""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()

    allowed_domains = (
        "yande.re",
        "konachan.com",
        "konachan.net",
        "safebooru.org",
        "zerochan.net",
        "gelbooru.com",
    )
    if not any(host == d or host.endswith("." + d) for d in allowed_domains):
        raise HTTPException(status_code=400, detail="Дозволено лише підтримувані домени Booru")

    if "gelbooru.com" in host:
        referer = "https://gelbooru.com/"
    elif "zerochan.net" in host:
        referer = "https://www.zerochan.net/"
    elif "safebooru.org" in host:
        referer = "https://safebooru.org/"
    else:
        referer = f"{parsed.scheme}://{parsed.netloc}/"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Referer": referer,
    }
    if "zerochan" in host:
        headers["User-Agent"] = "DownloaderApp - AntiGravityUser"

    session = await downloader.booru_service._get_session()

    # Створюємо список можливих URL на випадок розбіжності розширення (.png замість .jpg) або відсутності sample_
    candidate_urls = [url]
    if "gelbooru.com" in host:
        if "/samples/" in url:
            base_img = url.replace("/samples/", "/images/").replace("sample_", "")
            candidate_urls.append(base_img.replace(".jpg", ".png"))
            candidate_urls.append(base_img)
            candidate_urls.append(base_img.replace(".jpg", ".jpeg"))
            candidate_urls.append(base_img.replace(".jpg", ".gif"))
            # Також прев'ю як резервний варіант
            candidate_urls.append(url.replace("/samples/", "/thumbnails/").replace("sample_", "thumbnail_"))
        elif "/images/" in url:
            if url.endswith(".jpg"):
                candidate_urls.append(url.replace(".jpg", ".png"))
                candidate_urls.append(url.replace(".jpg", ".jpeg"))
            elif url.endswith(".png"):
                candidate_urls.append(url.replace(".png", ".jpg"))

    for candidate in candidate_urls:
        try:
            async with session.get(candidate, headers=headers) as resp:
                if resp.status == 200:
                    ctype = resp.headers.get("Content-Type", "image/jpeg")
                    if "text" in ctype or "html" in ctype:
                        continue
                    body = await resp.read()
                    return Response(
                        content=body,
                        media_type=ctype,
                        headers={"Cache-Control": "public, max-age=86400"},
                    )
        except Exception:
            continue

    raise HTTPException(status_code=404, detail="Не вдалося завантажити зображення з Booru")


@router.post("/api/v1/booru/download", response_model=TaskProgress)
async def start_booru_download(req: BooruDownloadRequest) -> TaskProgress:
    """Пошук та пакетне завантаження ілюстрацій з обраного Booru-сервісу."""
    prov = (req.provider or "yande.re").lower().strip()
    plat_name = downloader.booru_service._get_provider_display_name(prov)

    # Автоматичне маркування підключення (web, booru) та конкретного провайдера
    tag_set = set(req.user_tags or [t for t in req.tags.split() if t])
    tag_set.add("web")
    tag_set.add("booru")
    tag_set.add(prov.replace(".", "_"))
    if req.safe_mode:
        tag_set.add("safe_mode")

    task_id = str(uuid.uuid4())[:8]
    initial_progress = TaskProgress(
        task_id=task_id,
        url=f"booru:{prov}:{req.tags}",
        title=f"{plat_name}: {req.tags}",
        media_type="gallery",
        source_platform=plat_name,
        status=TaskStatus.EXTRACTING,
        tags=sorted(list(tag_set)),
    )
    tasks_state[task_id] = initial_progress
    await broadcast_progress(initial_progress)

    async def _run_booru() -> None:
        if req.download_all:
            page_media = await downloader.booru_service.fetch_all_posts_by_tag(
                provider=prov,
                tags=req.tags,
                max_pages=req.max_pages or 10,
                per_page=100,
                safe_mode=req.safe_mode,
                safe_tags=req.safe_tags,
                non_safe_tags=req.non_safe_tags,
            )
        else:
            page_media = await downloader.booru_service.fetch_posts(
                provider=prov,
                tags=req.tags,
                limit=req.limit,
                safe_mode=req.safe_mode,
                safe_tags=req.safe_tags,
                non_safe_tags=req.non_safe_tags,
            )

        if not page_media or not page_media.items:
            initial_progress.status = TaskStatus.FAILED
            initial_progress.error = f"За тегами «{req.tags}» на {plat_name} нічого не знайдено."
            await broadcast_progress(initial_progress)
            return

        res = await downloader.direct.download_items(
            task_id=task_id,
            source_url=f"booru:{prov}:{req.tags}",
            items=page_media.items,
            title=page_media.title,
            description=page_media.description,
            source_platform=plat_name,
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

        res.tags = sorted(list(tag_set))
        await downloader.storage.save_task_metadata(task_id, res)
        await broadcast_progress(res)

    asyncio.create_task(_run_booru())
    return initial_progress

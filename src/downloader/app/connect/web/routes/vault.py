from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
import zipfile
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from downloader.app.config.constants import IMAGE_EXTENSIONS
from downloader.app.connect.web.state import broadcast_progress, downloader
from downloader.app.core.accounts import account_manager
from downloader.app.core.dto.task import TaskProgress
from downloader.app.service.compression.transcoder import process_image
from downloader.app.service.storage.base import VaultFileItem

router = APIRouter(tags=["Vault"])


def _get_active_storage():
    """Повертає сховище поточного активного акаунту (або загальне системне)."""
    return account_manager.get_storage_for_account(
        account_id=account_manager.active_web_account_id,
        default_storage=downloader.storage,
    )


class DirectUploadPayload(BaseModel):
    filename: str
    content_b64: str
    tags: str = ""
    image_format: str = "original"
    image_max_side: int | None = None


@router.post("/api/v1/upload", response_model=TaskProgress)
async def upload_file_to_vault(payload: DirectUploadPayload) -> TaskProgress:
    """Завантаження локального файлу напряму у сховище через веб-інтерфейс."""
    storage = _get_active_storage()
    tag_list = list(dict.fromkeys(["web", "web_upload", *[t.strip().lstrip("#") for t in payload.tags.split(",") if t.strip()]]))
    prog = await storage.save_uploaded_base64_file(
        filename=payload.filename,
        content_b64=payload.content_b64,
        tags=tag_list,
    )

    fmt = (payload.image_format or "original").lower().strip()
    max_s = payload.image_max_side if payload.image_max_side and payload.image_max_side > 0 else None
    if (fmt != "original" or max_s) and prog.file_path:
        p = Path(prog.file_path)
        if p.suffix.lower() in IMAGE_EXTENSIONS:
            processed = await process_image(p, target_format=fmt, max_side=max_s)
            prog.file_path = str(processed)
            prog.file_paths = [str(processed)]
            prog.title = processed.name
            await storage.save_task_metadata(prog.task_id, prog)

    await broadcast_progress(prog)
    return prog


@router.get("/api/v1/files", response_model=list[VaultFileItem])
async def list_vault_files() -> list[VaultFileItem]:
    """Повертає список усіх збережених файлів у сховищі разом із метаданими та тегами."""
    storage = _get_active_storage()
    return await storage.list_files()


@router.get("/api/v1/files/view/{file_path:path}")
async def view_vault_file(file_path: str) -> FileResponse:
    """Перегляд файлу прямо в браузері (inline)."""
    storage = _get_active_storage()
    try:
        if hasattr(storage, "get_or_download_file"):
            target = await storage.get_or_download_file(file_path)
        else:
            target = storage.resolve_path(file_path)
    except FileNotFoundError:
        # Спроба пошуку в глобальному сховищі, якщо файл створено в іншій сесії
        try:
            if hasattr(downloader.storage, "get_or_download_file"):
                target = await downloader.storage.get_or_download_file(file_path)
            else:
                target = downloader.storage.resolve_path(file_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Файл не знайдено у сховищі")
    return FileResponse(target, media_type=None, content_disposition_type="inline")


@router.get("/api/v1/files/download/{file_path:path}")
async def download_vault_file(file_path: str) -> FileResponse:
    """Скачування файлу зі сховища на пристрій користувача (attachment)."""
    storage = _get_active_storage()
    try:
        if hasattr(storage, "get_or_download_file"):
            target = await storage.get_or_download_file(file_path)
        else:
            target = storage.resolve_path(file_path)
    except FileNotFoundError:
        try:
            if hasattr(downloader.storage, "get_or_download_file"):
                target = await downloader.storage.get_or_download_file(file_path)
            else:
                target = downloader.storage.resolve_path(file_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Файл не знайдено у сховищі")
    return FileResponse(target, filename=target.name, content_disposition_type="attachment")


class BatchDownloadPayload(BaseModel):
    relative_paths: list[str]


class BatchDeletePayload(BaseModel):
    relative_paths: list[str]


@router.post("/api/v1/files/batch-delete")
async def batch_delete_vault_files(payload: BatchDeletePayload) -> dict[str, Any]:
    """Пакетне видалення вибраних файлів зі сховища."""
    if not payload.relative_paths:
        raise HTTPException(status_code=400, detail="Список файлів для видалення порожній")

    deleted: list[str] = []
    failed: list[str] = []

    for rel in payload.relative_paths:
        try:
            ok = await downloader.storage.delete_file(rel)
            if ok:
                deleted.append(rel)
            else:
                failed.append(rel)
        except Exception:
            failed.append(rel)

    return {
        "status": "ok",
        "deleted_count": len(deleted),
        "failed_count": len(failed),
        "deleted": deleted,
        "failed": failed,
    }


@router.post("/api/v1/files/batch-zip")
async def batch_download_zip(payload: BatchDownloadPayload) -> FileResponse:
    """Створює ZIP-архів із обраних файлів сховища для пакетного скачування в браузер."""
    if not payload.relative_paths:
        raise HTTPException(status_code=400, detail="Список файлів порожній")

    tmp = NamedTemporaryFile(delete=False, suffix=".zip", prefix="vault_batch_")
    tmp_path = Path(tmp.name)
    tmp.close()

    added_names: set[str] = set()
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in payload.relative_paths:
            try:
                target = downloader.storage.resolve_path(rel)
                if target.is_file():
                    base_name = target.name
                    unique_name = base_name
                    counter = 1
                    while unique_name in added_names:
                        p = Path(base_name)
                        unique_name = f"{p.stem}_{counter}{p.suffix}"
                        counter += 1
                    added_names.add(unique_name)
                    zf.write(target, arcname=unique_name)
            except Exception:
                continue

    if not added_names:
        if tmp_path.exists():
            tmp_path.unlink()
        raise HTTPException(status_code=404, detail="Жоден із вказаних файлів не знайдено")

    return FileResponse(
        tmp_path,
        filename=f"vault_export_{len(added_names)}_files.zip",
        media_type="application/zip",
        content_disposition_type="attachment",
    )


@router.delete("/api/v1/files/{file_path:path}")
async def delete_vault_file(file_path: str) -> dict[str, Any]:
    """Видалення файлу зі сховища."""
    success = await downloader.storage.delete_file(file_path)
    if not success:
        raise HTTPException(status_code=404, detail="Файл не знайдено або не вдалося видалити")
    return {"status": "ok", "deleted": file_path}


class UpdateFileTagsPayload(BaseModel):
    relative_path: str
    tags: list[str]


@router.post("/api/v1/files/tags")
async def update_file_tags(payload: UpdateFileTagsPayload) -> dict[str, Any]:
    """Оновлення, додавання або видалення тегів файлу в сховищі."""
    updated = await downloader.storage.update_file_tags(payload.relative_path, payload.tags)
    return {
        "status": "ok",
        "relative_path": payload.relative_path,
        "tags": updated,
    }



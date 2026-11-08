import base64
import json
import os
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import quote, unquote
import uuid
import aiofiles

from downloader.app.config.constants import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
)
from downloader.app.core.dto.task import TaskProgress, TaskStatus
from downloader.app.core.platforms import detect_source_platform, get_image_dimensions
from downloader.app.service.download.base import sanitize_filename
from downloader.app.service.storage.base import BaseStorageProvider, VaultFileItem

META_FILENAME = ".meta.json"


def detect_media_type(ext: str) -> str:
    ext = ext.lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    return "document"


class LocalVaultStorage(BaseStorageProvider):
    """Локальне сховище медіафайлів зі збереженням метаданих та тегів у .meta.json."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def resolve_path(self, relative_path: str) -> Path:
        base_resolved = self.base_dir.resolve()
        # Автоматично декодуємо URL-символи, якщо шлях передано у відсотковому кодуванні (напр. %20, %23)
        decoded = unquote(relative_path).lstrip("/")
        target = (base_resolved / decoded).resolve()
        if not str(target).startswith(str(base_resolved)) or not target.is_file():
            # Додаткова перевірка без unquote на випадок, якщо файл вже містить такий символ на диску
            raw_target = (base_resolved / relative_path.lstrip("/")).resolve()
            if str(raw_target).startswith(str(base_resolved)) and raw_target.is_file():
                return raw_target
            raise FileNotFoundError(f"Файл не знайдено: {relative_path}")
        return target

    async def find_existing_file_by_name(self, filename: str) -> Path | None:
        """
        Перевіряє сховище на наявність файлу з ідентичною назвою (наприклад, yande.re_123456_... або video [ID].mp4).
        Повертає абсолютний Path до існуючого файлу, якщо такий є.
        """
        if not filename:
            return None
        target_name = filename.strip().lower()
        # Також перевіряємо чистий Booru ID для всіх провайдерів (yande.re, konachan, safebooru, zerochan, gelbooru)
        booru_m = re.search(r"(?:yande[_\.]?re|konachan|safebooru|zerochan|gelbooru)[_\.](\d+)", target_name, re.I)
        booru_id = booru_m.group(1) if booru_m else None

        base_resolved = self.base_dir.resolve()
        for task_dir in base_resolved.iterdir():
            if not task_dir.is_dir():
                continue
            for f in task_dir.iterdir():
                if f.is_file() and f.name != META_FILENAME:
                    f_lower = f.name.lower()
                    if f_lower == target_name:
                        return f
                    if booru_id:
                        f_booru = re.search(r"(?:yande[_\.]?re|konachan|safebooru|zerochan|gelbooru)[_\.](\d+)", f_lower, re.I)
                        if f_booru and f_booru.group(1) == booru_id:
                            return f
        return None

    async def delete_file(self, relative_path: str) -> bool:
        """Видаляє вказаний файл зі сховища та очищає порожню папку задачі."""
        try:
            target = self.resolve_path(relative_path)
            task_dir = target.parent
            if target.is_file():
                target.unlink()
            
            # Якщо у папці задачі залишився лише .meta.json або папка стала порожньою — прибираємо її
            base_resolved = self.base_dir.resolve()
            if task_dir != base_resolved and str(task_dir.resolve()).startswith(str(base_resolved)):
                remaining = [p for p in task_dir.iterdir() if p.name != META_FILENAME]
                if not remaining:
                    meta_p = task_dir / META_FILENAME
                    if meta_p.is_file():
                        meta_p.unlink()
                    task_dir.rmdir()
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    async def save_task_metadata(
        self,
        task_id: str,
        progress: TaskProgress,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Зберігає метадані завантаження (теги, джерело, назву, опис) поруч із файлами."""
        task_dir = self.base_dir / task_id
        if not task_dir.exists():
            return
        meta_path = task_dir / META_FILENAME
        payload: dict[str, Any] = {
            "task_id": task_id,
            "url": progress.url,
            "title": progress.title,
            "description": progress.description,
            "source_platform": progress.source_platform,
            "media_type": progress.media_type,
            "tags": progress.tags or [],
            "saved_at": time.time(),
        }
        if extra:
            payload.update(extra)
        try:
            async with aiofiles.open(meta_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(payload, ensure_ascii=False, indent=2))
        except Exception:
            pass

    async def update_file_tags(self, relative_path: str, tags: list[str]) -> list[str]:
        """Оновлює або редагує список тегів файлу в локальному сховищі."""
        clean_tags = sorted(list({
            str(t).strip().lower().lstrip("#")
            for t in tags
            if str(t).strip() and len(str(t).strip()) >= 2
        }))

        parts = relative_path.split("/")
        task_id = parts[0] if len(parts) > 1 else ""

        if task_id:
            task_dir = self.base_dir / task_id
            task_dir.mkdir(parents=True, exist_ok=True)
            meta_path = task_dir / META_FILENAME
        else:
            meta_path = self.base_dir / f"{relative_path}.meta.json"

        meta_data: dict[str, Any] = {}
        if meta_path.exists():
            try:
                meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta_data = {}

        meta_data["tags"] = clean_tags
        meta_data["updated_at"] = time.time()
        try:
            meta_path.write_text(json.dumps(meta_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Не вдалося оновити .meta.json: %s", exc)

        return clean_tags

    async def save_uploaded_base64_file(
        self,
        filename: str,
        content_b64: str,
        tags: list[str] | None = None,
    ) -> TaskProgress:
        """Зберігає завантажений через браузер файл разом із метаданими."""
        task_id = str(uuid.uuid4())[:8]
        task_dir = self.base_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        orig_path = Path(filename or f"upload_{task_id}")
        ext = orig_path.suffix.lower() or ".bin"
        safe_stem = sanitize_filename(orig_path.stem, max_len=75)
        dest_file = task_dir / f"{safe_stem}{ext}"

        # Відрізаємо префікс data:*/*;base64, якщо він переданий
        if "," in content_b64 and content_b64.strip().startswith("data:"):
            content_b64 = content_b64.split(",", 1)[1]

        raw_data = base64.b64decode(content_b64)
        file_bytes = len(raw_data)

        async with aiofiles.open(dest_file, "wb") as f:
            await f.write(raw_data)

        mtype = detect_media_type(ext)
        clean_tags = [t.strip().lstrip("#") for t in (tags or []) if t.strip()]

        prog = TaskProgress(
            task_id=task_id,
            url="web:upload",
            status=TaskStatus.COMPLETED,
            media_type=mtype,
            source_platform="Web Upload",
            title=dest_file.name,
            file_path=str(dest_file),
            file_paths=[str(dest_file)],
            tags=clean_tags,
            percent=100.0,
            downloaded_mb=round(file_bytes / (1024 * 1024), 2),
            total_mb=round(file_bytes / (1024 * 1024), 2),
        )
        await self.save_task_metadata(task_id, prog)
        return prog

    async def list_files(self) -> list[VaultFileItem]:
        """Сканує сховище, підтягує збережені теги та метадані з .meta.json."""
        if not self.base_dir.exists():
            return []

        items: list[VaultFileItem] = []
        meta_cache: dict[str, dict[str, Any]] = {}

        for root, _, files in os.walk(self.base_dir):
            root_path = Path(root)
            meta_file = root_path / META_FILENAME
            dir_key = str(root_path)
            if dir_key not in meta_cache:
                if meta_file.is_file():
                    try:
                        meta_cache[dir_key] = json.loads(meta_file.read_text(encoding="utf-8"))
                    except Exception:
                        meta_cache[dir_key] = {}
                else:
                    meta_cache[dir_key] = {}

            meta = meta_cache[dir_key]

            files_meta = meta.get("files_meta") or {}

            for f in files:
                if f.startswith(".") or f.endswith((".part", ".ytdl", ".temp", ".json")):
                    continue
                full_path = root_path / f
                try:
                    stat = full_path.stat()
                    if stat.st_size == 0:
                        continue
                    rel_path = full_path.relative_to(self.base_dir).as_posix()
                    ext = full_path.suffix.lower().lstrip(".")
                    mtype = detect_media_type(ext)

                    file_meta = files_meta.get(f) or {}

                    raw_tags = meta.get("tags") or []
                    tags_set: set[str] = set()
                    for t in raw_tags:
                        clean = str(t).strip().lower().lstrip("#")
                        if clean and len(clean) >= 2:
                            tags_set.add(clean)

                    # Додаємо індивідуальні теги конкретного файлу з files_meta (наприклад, номер 0001)
                    if file_meta and "tags" in file_meta:
                        for t in file_meta["tags"]:
                            clean = str(t).strip().lower().lstrip("#")
                            if clean:
                                tags_set.add(clean)

                    # Якщо назва файлу починається з 4 цифр (0001, 0002...), гарантовано додаємо тег номера
                    match_idx = re.match(r"^(\d{4})[-_\s]", f)
                    if match_idx:
                        tags_set.add(match_idx.group(1))

                    # Якщо у метаданих є плейлист, додаємо тег назви плейлиста
                    p_title = meta.get("playlist_title") or file_meta.get("playlist_title")
                    if p_title:
                        clean_p = re.sub(r"[^\w\s-]", "", p_title).strip().lower().replace(" ", "_")
                        if clean_p and len(clean_p) >= 2:
                            tags_set.add(clean_p)

                    # Якщо це окремий файл із назвою виду yande.re_<id>_<tags>, витягуємо його власні точні теги
                    if "yande.re" in f.lower():
                        tags_set.add("yande.re")
                        stem = full_path.stem
                        clean_stem = re.sub(r'^(?:\d+_)?yande\.re_\d+[_]?', '', stem)
                        for part in re.split(r'[\s_]+', clean_stem):
                            clean = part.strip().lower().lstrip("#")
                            if clean and len(clean) >= 2 and not clean.isdigit():
                                tags_set.add(clean)

                    tags_list = sorted(list(tags_set))

                    # Безпечне кодування шляху для браузера, щоб символи '#', '?' тощо не ломали URL
                    safe_url_path = "/".join(quote(part) for part in rel_path.split("/"))

                    effective_platform = detect_source_platform(
                        url=meta.get("url"),
                        name=meta.get("title") or f,
                        tags=tags_list,
                        existing_platform=meta.get("source_platform"),
                    )

                    w = meta.get("width")
                    h = meta.get("height")
                    if (not w or not h) and mtype == "image":
                        w, h = get_image_dimensions(full_path)

                    items.append(
                        VaultFileItem(
                            name=f,
                            title=meta.get("title") or f,
                            relative_path=rel_path,
                            extension=ext or "bin",
                            size_bytes=stat.st_size,
                            size_mb=round(stat.st_size / (1024 * 1024), 2),
                            modified_ts=stat.st_mtime,
                            media_type=mtype,
                            source_url=meta.get("url"),
                            source_platform=effective_platform,
                            tags=tags_list,
                            width=w,
                            height=h,
                            view_url=f"/api/v1/files/view/{safe_url_path}",
                            download_url=f"/api/v1/files/download/{safe_url_path}",
                        )
                    )
                except Exception:
                    continue

        items.sort(key=lambda x: x.modified_ts, reverse=True)
        return items


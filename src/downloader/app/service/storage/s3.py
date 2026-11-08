import asyncio
import base64
import json
import logging
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import quote, unquote

import aioboto3
from botocore.client import Config
from botocore.exceptions import ClientError

from downloader.app.config.constants import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    MIME_TO_EXT,
    VIDEO_EXTENSIONS,
)
from downloader.app.core.dto.task import TaskProgress, TaskStatus
from downloader.app.core.platforms import detect_source_platform
from downloader.app.service.download.base import sanitize_filename
from downloader.app.service.storage.base import BaseStorageProvider, VaultFileItem

logger = logging.getLogger("downloader.storage.s3")


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


def guess_content_type(ext: str) -> str:
    ext = ext.lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    for mime, e in MIME_TO_EXT.items():
        if e.lower() == ext:
            return mime
    if ext == ".mp4":
        return "video/mp4"
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    if ext == ".gif":
        return "image/gif"
    if ext == ".mp3":
        return "audio/mpeg"
    return "application/octet-stream"


class S3StorageProvider(BaseStorageProvider):
    """
    Повноцінний асинхронний S3-провайдер для збереження, роздачі та керування медіафайлами у сховищі (SeaweedFS / MinIO / AWS S3).
    Зберігає кешовану копію у локальному кеш-каталозі для швидкого доступу та ffmpeg.
    """

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket_name: str = "vault",
        region_name: str = "us-east-1",
        cache_dir: Path | None = None,
    ):
        self.endpoint_url = endpoint_url.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket_name = bucket_name
        self.region_name = region_name
        self.cache_dir = cache_dir or Path("/tmp/downloads")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = aioboto3.Session()
        self._bucket_initialized = False

    def _get_client_kwargs(self) -> dict[str, Any]:
        return {
            "service_name": "s3",
            "endpoint_url": self.endpoint_url,
            "aws_access_key_id": self.access_key,
            "aws_secret_access_key": self.secret_key,
            "region_name": self.region_name,
            "config": Config(s3={"addressing_style": "path"}, signature_version="s3v4"),
        }

    async def ensure_bucket(self) -> None:
        if self._bucket_initialized:
            return
        try:
            async with self.session.client(**self._get_client_kwargs()) as s3:
                try:
                    await s3.head_bucket(Bucket=self.bucket_name)
                except ClientError:
                    try:
                        await s3.create_bucket(Bucket=self.bucket_name)
                    except Exception as exc:
                        logger.warning("Помилка створення S3 бакету '%s': %s", self.bucket_name, exc)
                self._bucket_initialized = True
        except Exception as exc:
            logger.error("Не вдалося підключитися до S3: %s", exc)

    def resolve_path(self, relative_path: str) -> Path:
        """
        Повертає локальний шлях до файлу. Якщо локального файлу немає в кеші — повертає шлях, куди його можна завантажити.
        """
        decoded = unquote(relative_path).lstrip("/")
        target = (self.cache_dir / decoded).resolve()
        if target.is_file():
            return target
        # Спроба з прямим ім'ям
        raw_target = (self.cache_dir / relative_path.lstrip("/")).resolve()
        if raw_target.is_file():
            return raw_target
        return target

    async def get_or_download_file(self, relative_path: str) -> Path:
        """Гарантує наявність файлу локально на диску: якщо немає в кеші, витягує з S3."""
        clean_key = unquote(relative_path).lstrip("/")
        local_path = (self.cache_dir / clean_key).resolve()
        if local_path.is_file() and local_path.stat().st_size > 0:
            return local_path

        local_path.parent.mkdir(parents=True, exist_ok=True)
        await self.ensure_bucket()

        async with self.session.client(**self._get_client_kwargs()) as s3:
            try:
                resp = await s3.get_object(Bucket=self.bucket_name, Key=clean_key)
                async with resp["Body"] as stream:
                    content = await stream.read()
                    local_path.write_bytes(content)
                return local_path
            except ClientError as exc:
                logger.error("Помилка завантаження файлу '%s' з S3: %s", clean_key, exc)
                raise FileNotFoundError(f"Файл {clean_key} не знайдено в S3")

    async def upload_file_from_disk(
        self,
        local_path: Path,
        relative_path: str,
        meta_dict: dict[str, Any] | None = None,
    ) -> bool:
        """Завантажує файл з локального диску в S3 разом з метаданими."""
        if not local_path.is_file():
            return False
        await self.ensure_bucket()

        clean_key = relative_path.lstrip("/")
        ext = local_path.suffix.lower().lstrip(".")
        content_type = guess_content_type(ext)

        try:
            content = local_path.read_bytes()
            async with self.session.client(**self._get_client_kwargs()) as s3:
                await s3.put_object(
                    Bucket=self.bucket_name,
                    Key=clean_key,
                    Body=content,
                    ContentType=content_type,
                )
            return True
        except Exception as exc:
            logger.error("Помилка завантаження файлу '%s' в S3: %s", clean_key, exc)
            return False

    async def save_task_metadata(self, task_id: str, progress: TaskProgress) -> None:
        """Зберігає метадані задачі локально та в S3 як .meta.json."""
        task_dir = self.cache_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        meta_file = task_dir / ".meta.json"

        existing_tags: set[str] = set()
        if meta_file.exists():
            try:
                old = json.loads(meta_file.read_text(encoding="utf-8"))
                for t in old.get("tags", []):
                    clean = str(t).strip().lower().lstrip("#")
                    if clean and len(clean) >= 2:
                        existing_tags.add(clean)
            except Exception:
                pass

        for t in progress.tags:
            clean = str(t).strip().lower().lstrip("#")
            if clean and len(clean) >= 2:
                existing_tags.add(clean)

        meta_data: dict[str, Any] = {
            "task_id": task_id,
            "url": progress.url,
            "title": progress.title,
            "description": progress.description,
            "source_platform": progress.source_platform,
            "media_type": progress.media_type,
            "tags": sorted(list(existing_tags)),
            "saved_at": time.time(),
        }

        meta_file.write_text(json.dumps(meta_data, ensure_ascii=False, indent=2), encoding="utf-8")

        # Також завантажуємо .meta.json та всі файли задачі в S3
        await self.ensure_bucket()
        try:
            async with self.session.client(**self._get_client_kwargs()) as s3:
                await s3.put_object(
                    Bucket=self.bucket_name,
                    Key=f"{task_id}/.meta.json",
                    Body=json.dumps(meta_data, ensure_ascii=False).encode("utf-8"),
                    ContentType="application/json",
                )

                # Синхронізуємо медіафайли задачі в S3
                for p_str in progress.file_paths or ([progress.file_path] if progress.file_path else []):
                    p = Path(p_str)
                    if p.is_file() and p.exists():
                        rel = f"{task_id}/{p.name}"
                        ext = p.suffix.lower().lstrip(".")
                        await s3.put_object(
                            Bucket=self.bucket_name,
                            Key=rel,
                            Body=p.read_bytes(),
                            ContentType=guess_content_type(ext),
                        )
        except Exception as exc:
            logger.warning("Помилка збереження метаданих у S3 для задачі '%s': %s", task_id, exc)

    async def update_file_tags(self, relative_path: str, tags: list[str]) -> list[str]:
        """Оновлює або редагує список тегів файлу в сховищі S3 та локальному кеші."""
        clean_tags = sorted(list({
            str(t).strip().lower().lstrip("#")
            for t in tags
            if str(t).strip() and len(str(t).strip()) >= 2
        }))

        parts = relative_path.split("/")
        task_id = parts[0] if len(parts) > 1 else ""

        if task_id:
            task_dir = self.cache_dir / task_id
            task_dir.mkdir(parents=True, exist_ok=True)
            meta_path = task_dir / ".meta.json"
        else:
            meta_path = self.cache_dir / f"{relative_path}.meta.json"

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
            logger.warning("Не вдалося оновити локальний .meta.json: %s", exc)

        await self.ensure_bucket()
        meta_s3_key = f"{task_id}/.meta.json" if task_id else f"{relative_path}.meta.json"
        try:
            async with self.session.client(**self._get_client_kwargs()) as s3:
                try:
                    s3_resp = await s3.get_object(Bucket=self.bucket_name, Key=meta_s3_key)
                    existing_s3 = json.loads(await s3_resp["Body"].read())
                    if isinstance(existing_s3, dict):
                        existing_s3["tags"] = clean_tags
                        existing_s3["updated_at"] = time.time()
                        meta_data = existing_s3
                except Exception:
                    pass

                await s3.put_object(
                    Bucket=self.bucket_name,
                    Key=meta_s3_key,
                    Body=json.dumps(meta_data, ensure_ascii=False).encode("utf-8"),
                    ContentType="application/json",
                )
        except Exception as exc:
            logger.error("Помилка збереження оновлених тегів у S3 для '%s': %s", relative_path, exc)

        return clean_tags

    async def find_existing_file_by_name(self, filename: str) -> Path | None:
        """Перевіряє наявність файлу з такою назвою локально або в S3."""
        if not filename:
            return None
        target_name = filename.strip().lower()
        booru_m = re.search(r"(?:yande[_\.]?re|konachan|safebooru|zerochan|gelbooru)[_\.](\d+)", target_name, re.I)
        booru_id = booru_m.group(1) if booru_m else None

        # 1. Перевірка локального кешу
        for task_dir in self.cache_dir.iterdir():
            if not task_dir.is_dir():
                continue
            for f in task_dir.iterdir():
                if f.is_file() and f.name != ".meta.json":
                    f_lower = f.name.lower()
                    if f_lower == target_name:
                        return f
                    if booru_id:
                        f_booru = re.search(r"(?:yande[_\.]?re|konachan|safebooru|zerochan|gelbooru)[_\.](\d+)", f_lower, re.I)
                        if f_booru and f_booru.group(1) == booru_id:
                            return f

        # 2. Перевірка S3
        await self.ensure_bucket()
        try:
            async with self.session.client(**self._get_client_kwargs()) as s3:
                paginator = s3.get_paginator("list_objects_v2")
                async for page in paginator.paginate(Bucket=self.bucket_name):
                    for obj in page.get("Contents", []):
                        key = obj["Key"]
                        fname = key.split("/")[-1].lower()
                        if fname.startswith(".") or fname.endswith(".meta.json"):
                            continue
                        if fname == target_name:
                            return await self.get_or_download_file(key)
                        if booru_id:
                            f_booru = re.search(r"(?:yande[_\.]?re|konachan|safebooru|zerochan|gelbooru)[_\.](\d+)", fname, re.I)
                            if f_booru and f_booru.group(1) == booru_id:
                                return await self.get_or_download_file(key)
        except Exception:
            pass

        return None

    async def save_uploaded_base64_file(
        self,
        filename: str,
        content_b64: str,
        tags: list[str] | None = None,
    ) -> TaskProgress:
        """Завантаження файлу через Web UI (Base64) напряму в S3."""
        safe_filename = sanitize_filename(Path(filename).stem) + Path(filename).suffix
        tag_list = [t.strip().lstrip("#") for t in (tags or []) if t.strip()]

        existing = await self.find_existing_file_by_name(safe_filename)
        if existing:
            task_id = existing.parent.name
            size_mb = round(existing.stat().st_size / (1024 * 1024), 2)
            prog = TaskProgress(
                task_id=task_id,
                url=f"vault:{existing.name}",
                status=TaskStatus.COMPLETED,
                media_type=detect_media_type(existing.suffix),
                source_platform="Сховище S3",
                title=existing.name,
                file_path=str(existing),
                file_paths=[str(existing)],
                tags=tag_list,
                percent=100.0,
                downloaded_mb=size_mb,
                total_mb=size_mb,
            )
            await self.save_task_metadata(task_id, prog)
            return prog

        task_id = f"up_{uuid.uuid4().hex[:6]}"
        task_dir = self.cache_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        local_path = task_dir / safe_filename

        raw_bytes = base64.b64decode(content_b64)
        local_path.write_bytes(raw_bytes)

        size_mb = round(len(raw_bytes) / (1024 * 1024), 2)
        prog = TaskProgress(
            task_id=task_id,
            url=f"upload:{safe_filename}",
            status=TaskStatus.COMPLETED,
            media_type=detect_media_type(local_path.suffix),
            source_platform="Web Upload",
            title=safe_filename,
            file_path=str(local_path),
            file_paths=[str(local_path)],
            tags=tag_list,
            percent=100.0,
            downloaded_mb=size_mb,
            total_mb=size_mb,
        )
        await self.save_task_metadata(task_id, prog)
        return prog

    async def delete_file(self, relative_path: str) -> bool:
        """Видаляє файл з локального кешу та з S3."""
        clean_key = unquote(relative_path).lstrip("/")
        deleted_s3 = False

        await self.ensure_bucket()
        try:
            async with self.session.client(**self._get_client_kwargs()) as s3:
                await s3.delete_object(Bucket=self.bucket_name, Key=clean_key)
                deleted_s3 = True
        except Exception as exc:
            logger.warning("Помилка видалення об'єкта '%s' з S3: %s", clean_key, exc)

        local_path = (self.cache_dir / clean_key).resolve()
        if local_path.is_file():
            try:
                local_path.unlink(missing_ok=True)
                parent = local_path.parent
                if parent != self.cache_dir and parent.exists():
                    leftover = [f for f in parent.iterdir() if f.name != ".meta.json"]
                    if not leftover:
                        for f in parent.iterdir():
                            f.unlink(missing_ok=True)
                        parent.rmdir()
            except Exception:
                pass

        return deleted_s3 or local_path.is_file()

    async def list_files(self) -> list[VaultFileItem]:
        """
        Повертає список усіх збережених файлів у S3 (або локальному кеші),
        об'єднуючи метадані, теги та прямі посилання на роздачу.
        """
        await self.ensure_bucket()
        items: list[VaultFileItem] = []
        seen_keys: set[str] = set()

        meta_cache: dict[str, dict[str, Any]] = {}

        try:
            async with self.session.client(**self._get_client_kwargs()) as s3:
                paginator = s3.get_paginator("list_objects_v2")
                all_objects: list[dict[str, Any]] = []
                async for page in paginator.paginate(Bucket=self.bucket_name):
                    all_objects.extend(page.get("Contents", []))

                # 1. Спочатку завантажуємо всі .meta.json
                for obj in all_objects:
                    key = obj["Key"]
                    if key.endswith("/.meta.json") or key == ".meta.json":
                        task_prefix = key.split("/")[0] if "/" in key else ""
                        try:
                            m_resp = await s3.get_object(Bucket=self.bucket_name, Key=key)
                            async with m_resp["Body"] as b:
                                meta_cache[task_prefix] = json.loads((await b.read()).decode("utf-8"))
                        except Exception:
                            pass

                # 2. Обробляємо медіафайли
                for obj in all_objects:
                    key = obj["Key"]
                    if key.startswith(".") or key.endswith(("/.meta.json", ".meta.json", ".part", ".ytdl", ".temp")):
                        continue

                    seen_keys.add(key)
                    fname = key.split("/")[-1]
                    task_prefix = key.split("/")[0] if "/" in key else ""
                    ext = Path(fname).suffix.lower().lstrip(".")
                    mtype = detect_media_type(ext)
                    size_bytes = int(obj.get("Size", 0))
                    if size_bytes == 0:
                        continue

                    modified_ts = obj.get("LastModified").timestamp() if obj.get("LastModified") else time.time()
                    meta = meta_cache.get(task_prefix, {})

                    # Теги
                    tags_set: set[str] = set()
                    for t in meta.get("tags") or []:
                        clean = str(t).strip().lower().lstrip("#")
                        if clean and len(clean) >= 2:
                            tags_set.add(clean)

                    files_meta = meta.get("files_meta") or {}
                    file_meta = files_meta.get(fname) or {}

                    if file_meta and "tags" in file_meta:
                        for t in file_meta["tags"]:
                            clean = str(t).strip().lower().lstrip("#")
                            if clean:
                                tags_set.add(clean)

                    match_idx = re.match(r"^(\d{4})[-_\s]", fname)
                    if match_idx:
                        tags_set.add(match_idx.group(1))

                    p_title = meta.get("playlist_title") or file_meta.get("playlist_title")
                    if p_title:
                        clean_p = re.sub(r"[^\w\s-]", "", p_title).strip().lower().replace(" ", "_")
                        if clean_p and len(clean_p) >= 2:
                            tags_set.add(clean_p)

                    fname_lower = fname.lower()
                    for prov in ("yande.re", "konachan", "safebooru", "zerochan"):
                        if prov in fname_lower:
                            tags_set.add(prov)
                            tags_set.add("booru")
                            stem = Path(fname).stem
                            clean_stem = re.sub(rf'^(?:\d+_)?{re.escape(prov)}_\d+[_]?', '', stem, flags=re.I)
                            for part in re.split(r'[\s_]+', clean_stem):
                                clean = part.strip().lower().lstrip("#")
                                if clean and len(clean) >= 2 and not clean.isdigit():
                                    tags_set.add(clean)

                    safe_url_path = "/".join(quote(part) for part in key.split("/"))

                    effective_platform = detect_source_platform(
                        url=meta.get("url"),
                        name=meta.get("title") or fname,
                        tags=list(tags_set),
                        existing_platform=meta.get("source_platform"),
                    )

                    items.append(
                        VaultFileItem(
                            name=fname,
                            title=meta.get("title") or fname,
                            relative_path=key,
                            extension=ext or "bin",
                            size_bytes=size_bytes,
                            size_mb=round(size_bytes / (1024 * 1024), 2),
                            modified_ts=modified_ts,
                            media_type=mtype,
                            source_url=meta.get("url"),
                            source_platform=effective_platform,
                            tags=sorted(list(tags_set)),
                            width=meta.get("width"),
                            height=meta.get("height"),
                            view_url=f"/api/v1/files/view/{safe_url_path}",
                            download_url=f"/api/v1/files/download/{safe_url_path}",
                        )
                    )
        except Exception as exc:
            logger.error("Помилка читання об'єктів з S3: %s", exc)

        # 3. Об'єднуємо з локальним кешем: додаємо файли, які є на диску, але ще не завантажені в S3 (відео, аудіо тощо)
        if self.cache_dir.exists():
            for task_dir in self.cache_dir.iterdir():
                if not task_dir.is_dir() or task_dir.name.startswith("."):
                    continue
                task_prefix = task_dir.name
                meta_file = task_dir / ".meta.json"
                local_meta: dict[str, Any] = {}
                if meta_file.exists():
                    try:
                        local_meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    except Exception:
                        pass

                for f in task_dir.iterdir():
                    if not f.is_file() or f.name.startswith(".") or f.name == ".meta.json":
                        continue
                    if f.suffix.lower() in (".part", ".ytdl", ".temp"):
                        continue

                    rel_key = f"{task_prefix}/{f.name}"
                    if rel_key in seen_keys:
                        continue
                    seen_keys.add(rel_key)

                    fname = f.name
                    ext = f.suffix.lower().lstrip(".")
                    mtype = detect_media_type(ext)
                    try:
                        f_stat = f.stat()
                        size_bytes = f_stat.st_size
                        modified_ts = f_stat.st_mtime
                    except Exception:
                        size_bytes = 0
                        modified_ts = time.time()

                    if size_bytes == 0:
                        continue

                    tags_set: set[str] = set()
                    for t in local_meta.get("tags") or []:
                        clean = str(t).strip().lower().lstrip("#")
                        if clean and len(clean) >= 2:
                            tags_set.add(clean)

                    fname_lower = fname.lower()
                    for prov in ("yande.re", "konachan", "safebooru", "zerochan"):
                        if prov in fname_lower:
                            tags_set.add(prov)
                            tags_set.add("booru")
                            stem = Path(fname).stem
                            clean_stem = re.sub(rf'^(?:\d+_)?{re.escape(prov)}_\d+[_]?', '', stem, flags=re.I)
                            for part in re.split(r'[\s_]+', clean_stem):
                                clean = part.strip().lower().lstrip("#")
                                if clean and len(clean) >= 2 and not clean.isdigit():
                                    tags_set.add(clean)

                    safe_url_path = "/".join(quote(part) for part in rel_key.split("/"))
                    effective_local_platform = detect_source_platform(
                        url=local_meta.get("url"),
                        name=local_meta.get("title") or fname,
                        tags=list(tags_set),
                        existing_platform=local_meta.get("source_platform"),
                    )

                    items.append(
                        VaultFileItem(
                            name=fname,
                            title=local_meta.get("title") or fname,
                            relative_path=rel_key,
                            extension=ext or "bin",
                            size_bytes=size_bytes,
                            size_mb=round(size_bytes / (1024 * 1024), 2),
                            modified_ts=modified_ts,
                            media_type=mtype,
                            source_url=local_meta.get("url"),
                            source_platform=effective_local_platform,
                            tags=sorted(list(tags_set)),
                            width=local_meta.get("width"),
                            height=local_meta.get("height"),
                            view_url=f"/api/v1/files/view/{safe_url_path}",
                            download_url=f"/api/v1/files/download/{safe_url_path}",
                        )
                    )

                    # Фонова синхронізація локального файлу в S3
                    try:
                        asyncio.create_task(self._sync_local_file_to_s3(rel_key, f, local_meta))
                    except Exception:
                        pass

        # Якщо в S3 пусто, але є файли в локальному каталозі (наприклад, перед міграцією)
        if not items and self.cache_dir.exists():
            from downloader.app.service.storage.local import LocalVaultStorage
            fallback = LocalVaultStorage(self.cache_dir)
            return await fallback.list_files()

        items.sort(key=lambda x: x.modified_ts, reverse=True)
        return items

    async def _sync_local_file_to_s3(self, key: str, local_path: Path, meta: dict[str, Any]) -> None:
        """Фонова синхронізація файлу з локального кешу в S3 бакет."""
        try:
            await self.ensure_bucket()
            async with self.session.client(**self._get_client_kwargs()) as s3:
                ext = local_path.suffix.lower().lstrip(".")
                await s3.put_object(
                    Bucket=self.bucket_name,
                    Key=key,
                    Body=local_path.read_bytes(),
                    ContentType=guess_content_type(ext),
                )
                task_prefix = key.split("/")[0] if "/" in key else ""
                if task_prefix and meta:
                    await s3.put_object(
                        Bucket=self.bucket_name,
                        Key=f"{task_prefix}/.meta.json",
                        Body=json.dumps(meta, ensure_ascii=False).encode("utf-8"),
                        ContentType="application/json",
                    )
                logger.info("Успішно синхронізовано локальний файл '%s' в S3", key)
        except Exception as exc:
            logger.debug("Синхронізація '%s' в S3 відкладена: %s", key, exc)

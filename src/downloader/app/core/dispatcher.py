from pathlib import Path
from urllib.parse import unquote, urlparse

from downloader.app.config.constants import (
    AUDIO_EXTENSIONS,
    DIRECT_MEDIA_DOMAINS,
    DOCUMENT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
)
from downloader.app.core.deduplication import normalize_url
from downloader.app.core.dto.media import MediaType
from downloader.app.core.dto.task import TaskProgress, TaskStatus
from downloader.app.core.platforms import detect_source_platform
from downloader.app.service.compression.transcoder import process_image
from downloader.app.service.download.base import ProgressCallback
from downloader.app.service.download.direct_stream import DirectStreamDownloader
from downloader.app.service.download.video_yt_dlp import YtDlpDownloader
from downloader.app.service.scrapers.booru import BooruService
from downloader.app.service.scrapers.gallery import GalleryScraper
from downloader.app.service.scrapers.web_static import StaticWebScraper
from downloader.app.config.settings import get_settings
from downloader.app.service.storage.base import BaseStorageProvider
from downloader.app.service.storage.local import LocalVaultStorage
from downloader.app.service.storage.s3 import S3StorageProvider


class MediaDispatcher:
    """
    Розумний маршрутизатор завантажень (Ports & Adapters Core):
    1. Прямі посилання на картинки/медіа/файли -> DirectStreamDownloader.
    2. Відеохостинги та соцмережі (YouTube, TikTok, X/Twitter, Reddit, Pinterest, Instagram) -> YtDlpDownloader.
    3. Якщо посилання веде на пост із картинкою/галереєю (X/Twitter, Pinterest, Reddit) -> GalleryScraper + DirectStreamDownloader.
    4. Звичайні веб-сайти з картинками/статтями -> StaticWebScraper (OpenGraph / основні зображення) + DirectStreamDownloader.
    """

    def __init__(self, temp_dir: Path, max_concurrent: int = 4):
        self.temp_dir = temp_dir
        self.ytdlp = YtDlpDownloader(temp_dir=temp_dir, max_concurrent=max_concurrent)
        self.direct = DirectStreamDownloader(temp_dir=temp_dir, max_concurrent=max_concurrent)
        self.gallery_scraper = GalleryScraper()
        self.web_scraper = StaticWebScraper()
        self.booru_service = BooruService()

        # Вибір провайдера сховища (Local або S3)
        settings = get_settings()
        if settings.STORAGE_BACKEND.lower() == "s3":
            self.storage: BaseStorageProvider = S3StorageProvider(
                endpoint_url=settings.S3_ENDPOINT_URL,
                access_key=settings.S3_ACCESS_KEY.get_secret_value() if hasattr(settings.S3_ACCESS_KEY, "get_secret_value") else str(settings.S3_ACCESS_KEY),
                secret_key=settings.S3_SECRET_KEY.get_secret_value() if hasattr(settings.S3_SECRET_KEY, "get_secret_value") else str(settings.S3_SECRET_KEY),
                bucket_name=settings.S3_BUCKET_NAME,
                region_name=settings.S3_REGION,
                cache_dir=temp_dir,
            )
        else:
            self.storage = LocalVaultStorage(base_dir=temp_dir)

    def _is_direct_extension_or_cdn(self, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        path = unquote(parsed.path or "").lower()
        ext = Path(path).suffix.lower()

        if host in DIRECT_MEDIA_DOMAINS and host != "v.redd.it":
            return True
        if ext in (IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS | DOCUMENT_EXTENSIONS):
            return True
        return False

    def _is_pinterest_or_social_post(self, url: str) -> bool:
        host = (urlparse(url).netloc or "").lower()
        path = (urlparse(url).path or "").lower()
        if "pinterest." in host or "pin.it" in host:
            return True
        if any(d in host for d in ("twitter.com", "x.com", "fxtwitter.com", "vxtwitter.com")):
            return True
        if "reddit.com" in host or "redd.it" in host:
            # Якщо це v.redd.it, то це пряме відео, яке чудово качає yt-dlp
            if "v.redd.it" not in host:
                return True
        return False

    async def download(
        self,
        task_id: str,
        url: str,
        max_height: int = 1080,
        audio_only: bool = False,
        on_progress: ProgressCallback | None = None,
        tags: list[str] | None = None,
        image_format: str = "original",
        image_max_side: int | None = None,
        title: str | None = None,
        source_platform: str | None = None,
        download_playlist: bool = True,
    ) -> TaskProgress:
        tags = tags or []

        async def _apply_image_processing(res: TaskProgress) -> TaskProgress:
            """Застосовує зміну формату та роздільної здатності для завантажених зображень."""
            fmt = (image_format or "original").lower().strip()
            max_s = image_max_side if image_max_side and image_max_side > 0 else None
            if fmt == "original" and not max_s:
                return res

            if res.file_paths:
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
            elif res.file_path:
                p = Path(res.file_path)
                if p.suffix.lower() in IMAGE_EXTENSIONS:
                    processed = await process_image(p, target_format=fmt, max_side=max_s)
                    res.file_path = str(processed)
                    res.file_paths = [str(processed)]
            return res

        async def wrapped_progress(p: TaskProgress) -> None:
            if tags and not p.tags:
                p.tags = tags
            if on_progress:
                await on_progress(p)

        async def _finalize(res: TaskProgress, apply_img: bool = True) -> TaskProgress:
            if apply_img and res.status == TaskStatus.COMPLETED:
                res = await _apply_image_processing(res)
            # Якщо платформа досі не визначена або direct — визначаємо реальну платформу/сайт
            if not res.source_platform or res.source_platform.lower() in ("direct", "direct_stream", "unknown"):
                res.source_platform = detect_source_platform(
                    url=res.url or url,
                    name=res.title or title,
                    tags=res.tags or tags,
                    existing_platform=source_platform,
                )
            # Автоматичне маркування платформи та типу підключення у тегах
            tags_set = set(tags or [])
            if res.source_platform:
                clean_plat = res.source_platform.lower().replace(" ", "_").replace(".", "_")
                tags_set.add(clean_plat)
            # Додаємо всі теги, сформовані сервісом (наприклад, назву плейлиста)
            for t in (res.tags or []):
                clean_t = str(t).strip().lower().lstrip("#")
                if clean_t:
                    tags_set.add(clean_t)
            res.tags = sorted(list(tags_set))
            if res.status == TaskStatus.COMPLETED:
                extra_payload = {}
                if getattr(res, "files_meta", None):
                    extra_payload["files_meta"] = res.files_meta
                await self.storage.save_task_metadata(task_id, res, extra=extra_payload)
            return res

        # 0. Перевірка на Booru запит за тегами (наприклад: 'booru:landscape' або 'safebooru:cat?limit=5' або 'konachan:sky' або 'gelbooru:cat')
        booru_prefixes = ("booru:", "yande.re:", "konachan:", "safebooru:", "zerochan:", "gelbooru:")
        if url.startswith(booru_prefixes):
            prefix, rest = url.split(":", 1)
            prov = "yande.re"
            if prefix in ("konachan", "safebooru", "zerochan", "gelbooru"):
                prov = prefix
            elif ":" in rest:
                sub_prov, rest = rest.split(":", 1)
                prov = sub_prov.strip()

            booru_tags = rest.strip()
            limit = 10
            if "?" in booru_tags:
                booru_tags, query_str = booru_tags.split("?", 1)
                booru_tags = booru_tags.strip()
                from urllib.parse import parse_qs
                qs = parse_qs(query_str)
                if "limit" in qs and qs["limit"][0].isdigit():
                    limit = int(qs["limit"][0])

            page_media = await self.booru_service.fetch_posts(provider=prov, tags=booru_tags, limit=limit)
            if page_media and page_media.items:
                res = await self.direct.download_items(
                    task_id=task_id,
                    source_url=url,
                    items=page_media.items,
                    title=page_media.title,
                    description=page_media.description,
                    source_platform=page_media.platform or "Booru",
                    on_progress=wrapped_progress,
                )
                return await _finalize(res)

        clean_url = normalize_url(url)

        # 0.1. Якщо передано посилання на пост або пошук будь-якого Booru сайту
        booru_domains = ("yande.re", "konachan.com", "konachan.net", "safebooru.org", "zerochan.net", "gelbooru.com")
        if any(bd in clean_url for bd in booru_domains) and not self._is_direct_extension_or_cdn(clean_url):
            booru_media = await self.booru_service.extract(clean_url)
            if booru_media and booru_media.items:
                res = await self.direct.download_items(
                    task_id=task_id,
                    source_url=clean_url,
                    items=booru_media.items,
                    title=booru_media.title,
                    description=booru_media.description,
                    source_platform=booru_media.platform or "Booru",
                    on_progress=wrapped_progress,
                )
                return await _finalize(res)

        # 1. Перевірка на пряме посилання на картинку або файл за розширенням / CDN
        if not audio_only and self._is_direct_extension_or_cdn(clean_url):
            plat = detect_source_platform(url=clean_url, name=title, tags=tags, existing_platform=source_platform)
            res = await self.direct.download(
                task_id=task_id,
                url=clean_url,
                title=title,
                source_platform=plat,
                on_progress=wrapped_progress,
            )
            return await _finalize(res)

        # 2. Якщо це соцмережі (Pinterest, Twitter, Reddit) або відеохостинги:
        # Справжня гібридна комбінація:
        # Спочатку перевіряємо через yt-dlp на наявність повноцінного відео.
        # Якщо в пості знайдено відео — yt-dlp завантажує його зі звуком.
        # Якщо відео НЕ знайдено (yt-dlp повернув 'No video formats found!' або збій),
        # ми автоматично перехоплюємо це і витягуємо статичне фото/галерею найвищої якості через наші скрапери!

        async def ytdlp_silent_progress(p: TaskProgress) -> None:
            # Не спамимо у веб/ТГ помилками, якщо yt-dlp просто не знайшов відео на сторінці з фото
            if p.status == TaskStatus.FAILED:
                return
            await wrapped_progress(p)

        # Спроба 1: yt-dlp (відео та плейлисти)
        ytdlp_result = await self.ytdlp.download(
            task_id=task_id,
            url=clean_url,
            max_height=max_height,
            audio_only=audio_only,
            download_playlist=download_playlist,
            on_progress=ytdlp_silent_progress,
        )

        if ytdlp_result.status == TaskStatus.COMPLETED and ytdlp_result.file_path:
            return await _finalize(ytdlp_result, apply_img=False)

        # Якщо користувач просив суто аудіо (audio_only), а відеопотоку не знайдено — фото качати немає сенсу
        if audio_only:
            ytdlp_result.tags = tags
            await wrapped_progress(ytdlp_result)
            return ytdlp_result

        # Спроба 2: Галереї та фото-пости (Pinterest, Twitter, Reddit)
        if self._is_pinterest_or_social_post(clean_url):
            extracted_gallery = await self.gallery_scraper.extract(clean_url)
            if extracted_gallery and extracted_gallery.items:
                res = await self.direct.download_items(
                    task_id=task_id,
                    source_url=clean_url,
                    items=extracted_gallery.items,
                    title=extracted_gallery.title,
                    description=extracted_gallery.description,
                    source_platform=extracted_gallery.platform,
                    on_progress=wrapped_progress,
                )
                if res.status == TaskStatus.COMPLETED:
                    return await _finalize(res)

        # 4. Fallback A: Галереї та пости з картинками (якщо ще не перевірялися)
        extracted_gallery = await self.gallery_scraper.extract(clean_url)
        if extracted_gallery and extracted_gallery.items:
            res = await self.direct.download_items(
                task_id=task_id,
                source_url=clean_url,
                items=extracted_gallery.items,
                title=extracted_gallery.title,
                description=extracted_gallery.description,
                source_platform=extracted_gallery.platform,
                on_progress=wrapped_progress,
            )
            if res.status == TaskStatus.COMPLETED:
                return await _finalize(res)

        # 5. Fallback B: Перевірка HTTP Content-Type
        is_direct, _, final_url = await self.direct.probe_url(clean_url)
        if is_direct:
            plat = detect_source_platform(url=final_url, name=title, tags=tags, existing_platform=source_platform)
            res = await self.direct.download(
                task_id=task_id,
                url=final_url,
                source_platform=plat,
                on_progress=wrapped_progress,
            )
            if res.status == TaskStatus.COMPLETED:
                return await _finalize(res)

        # 6. Fallback C: Звичайний сайт зі статтею або картинкою
        extracted_web = await self.web_scraper.extract(clean_url)
        if extracted_web and extracted_web.items:
            res = await self.direct.download_items(
                task_id=task_id,
                source_url=clean_url,
                items=extracted_web.items[:5],
                title=extracted_web.title,
                description=extracted_web.description,
                source_platform=extracted_web.platform,
                on_progress=wrapped_progress,
            )
            if res.status == TaskStatus.COMPLETED:
                return await _finalize(res)

        # Якщо жоден метод не знайшов медіа — повертаємо помилку
        ytdlp_result.tags = tags
        if not ytdlp_result.error:
            ytdlp_result.error = "Не вдалося знайти відео або зображення за цим посиланням."
        await wrapped_progress(ytdlp_result)
        return ytdlp_result


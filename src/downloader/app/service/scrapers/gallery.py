from downloader.app.core.dto.media import ExtractedPageMedia
from downloader.app.service.scrapers.base import BaseScraper
from downloader.app.service.scrapers.gallery_dl import GalleryDlScraper
from downloader.app.service.scrapers.pinterest import PinterestScraper
from downloader.app.service.scrapers.reddit import RedditScraper
from downloader.app.service.scrapers.twitter import TwitterScraper


class GalleryScraper(BaseScraper):
    """
    Фасад-маршрутизатор для скраперів соцмереж та галерей.
    Кожна платформа реалізована в окремому ізольованому файлі:
    - pinterest.py (PinterestScraper)
    - twitter.py (TwitterScraper)
    - reddit.py (RedditScraper)
    - gallery_dl.py (GalleryDlScraper)
    """

    def __init__(self) -> None:
        self.scrapers: list[BaseScraper] = [
            PinterestScraper(),
            TwitterScraper(),
            RedditScraper(),
            GalleryDlScraper(),
        ]

    def can_handle(self, url: str) -> bool:
        return any(s.can_handle(url) for s in self.scrapers[:-1])

    async def extract(self, url: str) -> ExtractedPageMedia | None:
        for scraper in self.scrapers:
            if scraper.can_handle(url):
                res = await scraper.extract(url)
                if res and res.items:
                    return res
        return None

from abc import ABC, abstractmethod

from downloader.app.core.dto.media import ExtractedPageMedia


class BaseScraper(ABC):
    @abstractmethod
    async def extract(self, url: str) -> ExtractedPageMedia | None:
        raise NotImplementedError


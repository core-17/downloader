from abc import ABC, abstractmethod
from pathlib import Path
from pydantic import BaseModel, Field


class VaultFileItem(BaseModel):
    name: str
    title: str | None = None
    relative_path: str
    extension: str
    size_bytes: int
    size_mb: float
    modified_ts: float
    media_type: str
    source_url: str | None = None
    source_platform: str | None = None
    tags: list[str] = Field(default_factory=list)
    width: int | None = None
    height: int | None = None
    view_url: str
    download_url: str


class BaseStorageProvider(ABC):
    @abstractmethod
    async def list_files(self) -> list[VaultFileItem]:
        raise NotImplementedError

    @abstractmethod
    def resolve_path(self, relative_path: str) -> Path:
        raise NotImplementedError

    @abstractmethod
    async def delete_file(self, relative_path: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def update_file_tags(self, relative_path: str, tags: list[str]) -> list[str]:
        raise NotImplementedError


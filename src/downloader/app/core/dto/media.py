from enum import Enum
from pydantic import BaseModel, Field


class MediaType(str, Enum):
    VIDEO = "video"
    IMAGE = "image"
    GALLERY = "gallery"
    AUDIO = "audio"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


class ExtractedMediaItem(BaseModel):
    url: str
    media_type: MediaType = MediaType.IMAGE
    ext: str | None = None
    title: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class ExtractedPageMedia(BaseModel):
    source_url: str
    platform: str = "web"
    title: str | None = None
    description: str | None = None
    author: str | None = None
    items: list[ExtractedMediaItem] = Field(default_factory=list)


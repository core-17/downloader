from functools import lru_cache
from pathlib import Path
from typing import List
from pydantic import (
    Field,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    computed_field,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Downloader Vault"
    DEBUG: bool = False
    DOWNLOAD_TEMP_DIR: Path = Field(
        default=Path("/tmp/downloads"),
        description="Локальна директорія для чанків yt-dlp та склеювання торентів",
    )

    POSTGRES_DB: str = "downloader"
    POSTGRES_USER: str = "downloader_user"
    POSTGRES_PASSWORD: str = "secure_downloader_password"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None

    @computed_field  
    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: str | None = None

    @computed_field  
    @property
    def async_redis_url(self) -> str:
        if self.REDIS_URL:
            return self.REDIS_URL
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    S3_ENDPOINT_URL: str = "http://seaweedfs:8333"
    S3_ACCESS_KEY: SecretStr = SecretStr("any_access_key")
    S3_SECRET_KEY: SecretStr = SecretStr("any_secret_key")
    S3_BUCKET_NAME: str = "vault"
    S3_REGION: str = "us-east-1"

    TELEGRAM_BOT_TOKEN: SecretStr = Field(
        ...,
        description="Обов'язковий токен від @BotFather. Без нього бот не запуститься.",
    )
    TELEGRAM_ALLOWED_USERS: List[int] = Field(
        default_factory=list,
        description="Білий список Telegram ID. Парсить як рядок '123,456', так і JSON '[123, 456]'",
    )

    MAX_FILE_SIZE_CONFIRMATION_BYTES: int = Field(
        default=2 * 1024 * 1024 * 1024,  # 2 ГБ
        description="Поріг ваги файлу, після якого потрібне підтвердження користувача",
    )
    DEFAULT_VIDEO_QUALITY: str = "1080p"
    CONFIRMATION_TIMEOUT_SECONDS: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",        
        case_sensitive=False,  
    )


@lru_cache
def get_settings() -> Settings:

    return Settings()
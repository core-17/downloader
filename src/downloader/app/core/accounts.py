import hashlib
import json
import logging
from pathlib import Path
import time
from typing import Any
from pydantic import BaseModel, Field

from downloader.app.config.settings import get_settings
from downloader.app.service.storage.base import BaseStorageProvider
from downloader.app.service.storage.local import LocalVaultStorage
from downloader.app.service.storage.s3 import S3StorageProvider

logger = logging.getLogger("downloader.accounts")

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
ACCOUNTS_FILE = CONFIG_DIR / "accounts.json"
NSFW_TAGS_FILE = CONFIG_DIR / "nsfw_tags.json"
STATIC_NSFW_TAGS_FILE = Path(__file__).resolve().parent.parent / "connect" / "web" / "static" / "nsfw_tags.json"


class AccountApiKeys(BaseModel):
    gelbooru_user_id: str = ""
    gelbooru_api_key: str = ""
    yandere_login: str = ""
    yandere_api_key: str = ""
    konachan_login: str = ""
    konachan_api_key: str = ""
    zerochan_username: str = ""
    social_cookies: str = ""  # Cookies або токени для Twitter/X, Pinterest, Reddit, Instagram


class AccountBotBinding(BaseModel):
    telegram_user_ids: list[int] = Field(default_factory=list)
    discord_user_ids: list[int] = Field(default_factory=list)
    telegram_bot_token: str = ""
    discord_bot_token: str = ""
    social_login_handle: str = ""  # @username у Telegram, Discord або соцмережах


class AccountStorageConfig(BaseModel):
    backend: str = "s3"  # "s3" або "local"
    s3_bucket: str = "vault"
    s3_prefix: str = ""  # префікс/папка для зберігання файлів цього акаунта
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""


class UserAccount(BaseModel):
    id: str
    username: str
    display_name: str
    avatar_emoji: str = "👤"
    created_at: float = Field(default_factory=time.time)
    safe_mode_default: bool = False
    custom_nsfw_tags: list[str] = Field(default_factory=list)
    api_keys: AccountApiKeys = Field(default_factory=AccountApiKeys)
    bots: AccountBotBinding = Field(default_factory=AccountBotBinding)
    storage: AccountStorageConfig = Field(default_factory=AccountStorageConfig)


class AccountManager:
    """
    Менеджер звичайних користувацьких акаунтів:
    Кожен акаунт має власні API-ключі (Gelbooru, Yande.re тощо), прив'язку до ботів (Telegram/Discord)
    та конфігурацію власного сховища (папка або S3).
    """

    def __init__(self) -> None:
        self.accounts: dict[str, UserAccount] = {}
        self.active_web_account_id: str = "account_1"
        self._storage_instances: dict[str, BaseStorageProvider] = {}
        self._load_or_init_accounts()

    def _get_default_accounts(self) -> list[UserAccount]:
        settings = get_settings()
        tg_users = list(settings.TELEGRAM_ALLOWED_USERS or [])
        dc_users = list(settings.DISCORD_ALLOWED_USERS or [])
        gel_key = (
            settings.GELBOORU_API_KEY.get_secret_value()
            if hasattr(settings, "GELBOORU_API_KEY") and settings.GELBOORU_API_KEY
            else ""
        )
        gel_uid = (
            str(settings.GELBOORU_USER_ID)
            if hasattr(settings, "GELBOORU_USER_ID") and settings.GELBOORU_USER_ID
            else ""
        )

        return [
            UserAccount(
                id="account_1",
                username="account_1",
                display_name="Акаунт 1",
                avatar_emoji="👤",
                safe_mode_default=False,
                api_keys=AccountApiKeys(
                    gelbooru_user_id=gel_uid,
                    gelbooru_api_key=gel_key,
                ),
                bots=AccountBotBinding(
                    telegram_user_ids=tg_users,
                    discord_user_ids=dc_users,
                    social_login_handle="@user",
                ),
                storage=AccountStorageConfig(
                    backend=settings.STORAGE_BACKEND.lower(),
                    s3_bucket=settings.S3_BUCKET_NAME,
                    s3_prefix="",
                ),
            ),
            UserAccount(
                id="account_2",
                username="account_2",
                display_name="Акаунт 2",
                avatar_emoji="📁",
                safe_mode_default=False,
                bots=AccountBotBinding(
                    social_login_handle="",
                ),
                storage=AccountStorageConfig(
                    backend=settings.STORAGE_BACKEND.lower(),
                    s3_bucket=settings.S3_BUCKET_NAME,
                    s3_prefix="account_2",
                ),
            ),
        ]

    def _load_or_init_accounts(self) -> None:
        if ACCOUNTS_FILE.exists():
            try:
                raw = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
                acc_list = raw.get("accounts", [])
                self.active_web_account_id = raw.get("active_account_id", "account_1")
                for item in acc_list:
                    acc = UserAccount(**item)
                    self.accounts[acc.id] = acc
            except Exception as exc:
                logger.error("Помилка читання accounts.json: %s", exc)

        if not self.accounts:
            for acc in self._get_default_accounts():
                self.accounts[acc.id] = acc
            self.save_accounts()

        if self.active_web_account_id not in self.accounts:
            self.active_web_account_id = next(iter(self.accounts.keys()), "account_1")

    def save_accounts(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "active_account_id": self.active_web_account_id,
                "accounts": [acc.model_dump(mode="json") for acc in self.accounts.values()],
            }
            ACCOUNTS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.error("Не вдалося зберегти accounts.json: %s", exc)

    def list_accounts(self) -> list[UserAccount]:
        return list(self.accounts.values())

    def get_account(self, account_id: str | None = None) -> UserAccount:
        target_id = account_id or self.active_web_account_id
        if target_id in self.accounts:
            return self.accounts[target_id]
        return next(iter(self.accounts.values()))

    def get_current_account(self) -> UserAccount:
        return self.get_account()

    def get_account_by_telegram_id(self, tg_user_id: int) -> UserAccount:
        for acc in self.accounts.values():
            if tg_user_id in acc.bots.telegram_user_ids:
                return acc
        return self.get_account()

    def get_account_by_discord_id(self, dc_user_id: int) -> UserAccount:
        for acc in self.accounts.values():
            if dc_user_id in acc.bots.discord_user_ids:
                return acc
        return self.get_account()

    def set_active_account(self, account_id: str) -> UserAccount:
        if account_id not in self.accounts:
            raise ValueError(f"Акаунт '{account_id}' не знайдено")
        self.active_web_account_id = account_id
        self.save_accounts()
        return self.accounts[account_id]

    def create_or_update_account(self, data: dict[str, Any]) -> UserAccount:
        acc_id = str(data.get("id") or data.get("username") or f"account_{int(time.time())}").strip().lower()
        acc_id = "".join(c if c.isalnum() or c == "_" else "_" for c in acc_id)

        existing = self.accounts.get(acc_id)
        if existing:
            updated_dict = existing.model_dump()
            for k, v in data.items():
                if k in updated_dict and v is not None:
                    updated_dict[k] = v
            acc = UserAccount(**updated_dict)
        else:
            settings = get_settings()
            if "storage" not in data or not data["storage"]:
                data["storage"] = {
                    "backend": settings.STORAGE_BACKEND.lower(),
                    "s3_bucket": settings.S3_BUCKET_NAME,
                    "s3_prefix": acc_id,
                }
            acc = UserAccount(
                id=acc_id,
                username=data.get("username") or acc_id,
                display_name=data.get("display_name") or data.get("username") or acc_id,
                avatar_emoji=data.get("avatar_emoji") or "👤",
                safe_mode_default=bool(data.get("safe_mode_default", False)),
                custom_nsfw_tags=data.get("custom_nsfw_tags") or [],
                api_keys=AccountApiKeys(**(data.get("api_keys") or {})),
                bots=AccountBotBinding(**(data.get("bots") or {})),
                storage=AccountStorageConfig(**(data.get("storage") or {})),
            )

        self.accounts[acc.id] = acc
        self._storage_instances.pop(acc.id, None)
        self.save_accounts()
        return acc

    def delete_account(self, account_id: str) -> bool:
        if len(self.accounts) <= 1 or account_id not in self.accounts:
            return False
        del self.accounts[account_id]
        self._storage_instances.pop(account_id, None)
        if self.active_web_account_id == account_id:
            self.active_web_account_id = next(iter(self.accounts.keys()))
        self.save_accounts()
        return True

    def get_storage_for_account(self, account_id: str | None = None, default_storage: BaseStorageProvider | None = None) -> BaseStorageProvider:
        acc = self.get_account(account_id)
        if not acc.storage.s3_prefix and not acc.storage.s3_endpoint and default_storage is not None:
            return default_storage

        if acc.id in self._storage_instances:
            return self._storage_instances[acc.id]

        settings = get_settings()
        sub_folder = acc.storage.s3_prefix.strip("/")
        cache_dir = settings.DOWNLOAD_TEMP_DIR / sub_folder if sub_folder else settings.DOWNLOAD_TEMP_DIR
        cache_dir.mkdir(parents=True, exist_ok=True)

        if acc.storage.backend.lower() == "s3":
            endpoint = acc.storage.s3_endpoint or settings.S3_ENDPOINT_URL
            access_key = acc.storage.s3_access_key or (
                settings.S3_ACCESS_KEY.get_secret_value()
                if hasattr(settings.S3_ACCESS_KEY, "get_secret_value")
                else str(settings.S3_ACCESS_KEY)
            )
            secret_key = acc.storage.s3_secret_key or (
                settings.S3_SECRET_KEY.get_secret_value()
                if hasattr(settings.S3_SECRET_KEY, "get_secret_value")
                else str(settings.S3_SECRET_KEY)
            )
            bucket = acc.storage.s3_bucket or settings.S3_BUCKET_NAME
            provider: BaseStorageProvider = S3StorageProvider(
                endpoint_url=endpoint,
                access_key=access_key,
                secret_key=secret_key,
                bucket_name=bucket,
                region_name=settings.S3_REGION,
                cache_dir=cache_dir,
            )
        else:
            provider = LocalVaultStorage(base_dir=cache_dir)

        self._storage_instances[acc.id] = provider
        return provider

    def get_nsfw_config(self) -> dict[str, Any]:
        if NSFW_TAGS_FILE.exists():
            try:
                return json.loads(NSFW_TAGS_FILE.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.error("Помилка читання nsfw_tags.json: %s", exc)
        return {
            "nsfw_ratings": ["explicit", "questionable", "e", "q"],
            "nsfw_query_exclusions": {
                "yande.re": ["-rating:explicit", "-rating:questionable"],
                "konachan": ["-rating:explicit", "-rating:questionable"],
                "gelbooru": ["-rating:explicit", "-rating:questionable"],
                "safebooru": ["-nude", "-nipples", "-pussy", "-sex"],
                "zerochan": [],
            },
            "nsfw_tags": [
                "rating:explicit",
                "rating:questionable",
                "nsfw",
                "r-18",
                "nude",
                "naked",
                "nipples",
                "pussy",
                "penis",
                "sex",
                "cum",
                "anal",
                "fellatio",
                "paizuri",
                "masturbation",
                "cameltoe",
                "topless",
                "bottomless",
                "bondage",
                "bdsm",
                "ahegao",
                "futanari",
                "upskirt",
            ],
        }

    def get_nsfw_tags_list(self, account_id: str | None = None) -> list[str]:
        cfg = self.get_nsfw_config()
        base_tags = [str(t).strip().lower() for t in cfg.get("nsfw_tags", []) if str(t).strip()]
        acc = self.get_account(account_id)
        for ct in acc.custom_nsfw_tags:
            clean = ct.strip().lower()
            if clean and clean not in base_tags:
                base_tags.append(clean)
        return base_tags

    def update_nsfw_tags_list(self, tags: list[str]) -> dict[str, Any]:
        clean_tags = []
        for t in tags:
            for part in str(t).replace(",", " ").split():
                c = part.strip().lower().lstrip("-")
                if c and c not in clean_tags:
                    clean_tags.append(c)

        cfg = self.get_nsfw_config()
        cfg["nsfw_tags"] = clean_tags
        text = json.dumps(cfg, ensure_ascii=False, indent=2)
        try:
            NSFW_TAGS_FILE.write_text(text, encoding="utf-8")
            STATIC_NSFW_TAGS_FILE.write_text(text, encoding="utf-8")
        except Exception as exc:
            logger.error("Помилка запису nsfw_tags.json: %s", exc)
        return cfg


account_manager = AccountManager()

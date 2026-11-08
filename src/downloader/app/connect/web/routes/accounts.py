from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from downloader.app.core.accounts import account_manager

router = APIRouter(prefix="/api/v1/accounts", tags=["Accounts & APIs"])


class SwitchAccountPayload(BaseModel):
    account_id: str


class AccountSavePayload(BaseModel):
    id: str | None = None
    username: str
    display_name: str | None = None
    avatar_emoji: str | None = "👤"
    safe_mode_default: bool = False
    custom_nsfw_tags: list[str] = []
    api_keys: dict[str, Any] = {}
    bots: dict[str, Any] = {}
    storage: dict[str, Any] = {}


@router.get("")
async def list_accounts():
    """Отримати список усіх профілів та поточний активний акаунт."""
    accounts = account_manager.list_accounts()
    return {
        "active_account_id": account_manager.active_web_account_id,
        "accounts": [acc.model_dump(mode="json") for acc in accounts],
    }


@router.get("/current")
async def get_current_account():
    """Отримати налаштування активного акаунту."""
    acc = account_manager.get_account()
    return acc.model_dump(mode="json")


@router.post("/switch")
async def switch_active_account(payload: SwitchAccountPayload):
    """Швидке перемикання активного профілю в 1 клік."""
    try:
        acc = account_manager.set_active_account(payload.account_id)
        return {
            "status": "success",
            "active_account_id": acc.id,
            "account": acc.model_dump(mode="json"),
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/save")
async def save_account(payload: AccountSavePayload):
    """Створення нового або оновлення існуючого профілю з його API-ключами, ботами та сховищем."""
    try:
        acc = account_manager.create_or_update_account(payload.model_dump(exclude_unset=True))
        return {
            "status": "success",
            "account": acc.model_dump(mode="json"),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Помилка збереження акаунта: {exc}")


@router.delete("/{account_id}")
async def delete_account(account_id: str):
    """Видалення профілю (крім основного 'default')."""
    if account_id == "default":
        raise HTTPException(status_code=400, detail="Неможливо видалити основний системний акаунт")
    success = account_manager.delete_account(account_id)
    if not success:
        raise HTTPException(status_code=404, detail="Акаунт не знайдено")
    return {"status": "success", "deleted_id": account_id}

from fastapi import APIRouter

from downloader.app.connect.web.routes import booru, downloads, pages, vault, ws
from downloader.app.connect.web.state import (
    STATIC_DIR,
    broadcast_progress,
    downloader,
    tasks_state,
    ws_connections,
)

router = APIRouter()
router.include_router(pages.router)
router.include_router(downloads.router)
router.include_router(booru.router)
router.include_router(vault.router)
router.include_router(ws.router)

__all__ = [
    "STATIC_DIR",
    "broadcast_progress",
    "downloader",
    "router",
    "tasks_state",
    "ws_connections",
]

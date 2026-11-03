from pathlib import Path
from fastapi import WebSocket

from downloader.app.config.settings import get_settings
from downloader.app.core.dispatcher import MediaDispatcher
from downloader.app.core.dto.task import TaskProgress

_settings = get_settings()
STATIC_DIR = Path(__file__).resolve().parent / "static"

downloader = MediaDispatcher(temp_dir=_settings.DOWNLOAD_TEMP_DIR, max_concurrent=4)
tasks_state: dict[str, TaskProgress] = {}
ws_connections: set[WebSocket] = set()


async def broadcast_progress(progress: TaskProgress) -> None:
    """Зберігає стан задачі та розсилає прогрес усім активним WebSocket-клієнтам."""
    tasks_state[progress.task_id] = progress
    if not ws_connections:
        return

    payload = progress.model_dump(mode="json")
    dead_sockets: set[WebSocket] = set()
    for ws in ws_connections:
        try:
            await ws.send_json(payload)
        except Exception:
            dead_sockets.add(ws)
    ws_connections.difference_update(dead_sockets)


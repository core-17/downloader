import asyncio
import uuid
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from downloader.app.core.dto.task import DownloadRequest, TaskProgress
from downloader.app.service.download.video_yt_dlp import YtDlpDownloader

app = FastAPI(
    title="Universal Media Downloader API",
    version="0.1.0",
    description="Ядро завантаження з WebSocket-моніторингом",
)

downloader = YtDlpDownloader(temp_dir=Path("/tmp/downloads"), max_concurrent=4)
tasks_state: dict[str, TaskProgress] = {}
ws_connections: set[WebSocket] = set()


async def broadcast_progress(progress: TaskProgress) -> None:
    tasks_state[progress.task_id] = progress
    if not ws_connections:
        return

    payload = progress.model_dump(mode="json")
    dead_sockets = set()
    for ws in ws_connections:
        try:
            await ws.send_json(payload)
        except Exception:
            dead_sockets.add(ws)
    ws_connections.difference_update(dead_sockets)


@app.post("/api/v1/download", response_model=TaskProgress, tags=["Downloads"])
async def start_download(req: DownloadRequest):
    task_id = str(uuid.uuid4())[:8]
    initial_progress = TaskProgress(task_id=task_id, url=str(req.url))
    tasks_state[task_id] = initial_progress

    asyncio.create_task(
        downloader.download(
            task_id=task_id,
            url=str(req.url),
            max_height=req.max_height,
            on_progress=broadcast_progress,
        )
    )
    return initial_progress


@app.get("/api/v1/tasks", response_model=list[TaskProgress], tags=["Downloads"])
async def list_tasks():
    return list(tasks_state.values())


@app.websocket("/ws/progress")
async def websocket_progress_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_connections.add(websocket)
    try:
        for task in tasks_state.values():
            await websocket.send_json(task.model_dump(mode="json"))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_connections.discard(websocket)


@app.get("/monitor", response_class=HTMLResponse, tags=["UI Monitor"])
async def live_monitor_page():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Live Download Monitor</title>
        <style>
            body { font-family: system-ui, sans-serif; background: #121212; color: #e0e0e0; padding: 2rem; }
            .card { background: #1e1e1e; border: 1px solid #333; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
            .bar-bg { background: #333; height: 12px; border-radius: 6px; overflow: hidden; margin: 8px 0; }
            .bar-fill { background: #4caf50; height: 100%; transition: width 0.2s ease; }
            .meta { font-size: 0.85rem; color: #aaa; display: flex; justify-content: space-between; }
            .badge { padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.75rem; background: #2c3e50; }
        </style>
    </head>
    <body>
        <h2>📡 Live WebSocket Download Monitor</h2>
        <div id="tasks">Очікування завантажень...</div>
        <script>
            const tasks = {};
            const container = document.getElementById('tasks');
            const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            const ws = new WebSocket(`${proto}//${location.host}/ws/progress`);

            ws.onmessage = (event) => {
                const t = JSON.parse(event.data);
                tasks[t.task_id] = t;
                render();
            };

            function render() {
                container.innerHTML = Object.values(tasks).reverse().map(t => `
                    <div class="card">
                        <div style="display:flex; justify-content:space-between;">
                            <strong>${t.title || t.url}</strong>
                            <span class="badge">${t.status.toUpperCase()}</span>
                        </div>
                        <div class="bar-bg">
                            <div class="bar-fill" style="width: ${t.percent}%"></div>
                        </div>
                        <div class="meta">
                            <span>ID: ${t.task_id} | ${t.percent}% (${t.downloaded_mb} / ${t.total_mb || '?'} MB)</span>
                            <span>🚀 ${t.speed_mb_s} MB/s | ETA: ${t.eta_seconds ?? '-'}s</span>
                        </div>
                        ${t.file_path ? `<div style="color:#81c784; font-size:0.8rem; margin-top:4px;">💾 ${t.file_path}</div>` : ''}
                        ${t.error ? `<div style="color:#e57373; font-size:0.8rem; margin-top:4px;">❌ ${t.error}</div>` : ''}
                    </div>
                `).join('');
            }
        </script>
    </body>
    </html>
    """
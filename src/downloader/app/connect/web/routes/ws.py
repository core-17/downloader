from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from downloader.app.connect.web.state import tasks_state, ws_connections

router = APIRouter()


@router.websocket("/ws/progress")
async def websocket_progress_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    ws_connections.add(websocket)
    try:
        for task in tasks_state.values():
            await websocket.send_json(task.model_dump(mode="json"))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_connections.discard(websocket)


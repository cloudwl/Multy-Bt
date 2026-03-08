from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.deps import events
from app.routes import adapters, agents, approvals, runs, tasks, workspaces

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"

app = FastAPI(title="Multy-Bt", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(runs.router, prefix="/api/v1")
app.include_router(approvals.router, prefix="/api/v1")
app.include_router(adapters.router, prefix="/api/v1")
app.include_router(workspaces.router, prefix="/api/v1")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(INDEX_FILE)


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "multy-bt"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        async for message in events.subscribe():
            await websocket.send_json(message)
    except WebSocketDisconnect:
        return

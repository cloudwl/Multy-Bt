from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.deps import runner, store
from app.models import ClaudeLaunchRequest, CodexLaunchRequest, Run

router = APIRouter(prefix="/adapters", tags=["adapters"])


@router.post("/codex/launch", response_model=Run)
async def launch_codex(payload: CodexLaunchRequest) -> Run:
    if store.get_task(payload.task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        return await runner.launch_codex(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/claude/launch", response_model=Run)
async def launch_claude(payload: ClaudeLaunchRequest) -> Run:
    if store.get_task(payload.task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        return await runner.launch_claude(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

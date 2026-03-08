from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.deps import store, workspace_manager
from app.models import Workspace, WorkspaceCreateRequest

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=list[Workspace])
async def list_workspaces() -> list[Workspace]:
    return store.list_workspaces()


@router.get("/{workspace_id}", response_model=Workspace)
async def get_workspace(workspace_id: str) -> Workspace:
    workspace = store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.post("", response_model=Workspace)
async def create_workspace(payload: WorkspaceCreateRequest) -> Workspace:
    if store.get_task(payload.task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        return await workspace_manager.create_for_task(payload.task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

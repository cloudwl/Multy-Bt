from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.store import make_id, now_ms
from app.deps import events, store, workspace_manager
from app.models import (
    AssignRequest,
    HandoffRequest,
    MessageCreate,
    Task,
    TaskContextSummary,
    TaskCreate,
    TaskMessage,
    TaskStatus,
    TaskUpdate,
    Workspace,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[Task])
async def list_tasks(status: TaskStatus | None = None) -> list[Task]:
    return store.list_tasks(status=status)


@router.post("", response_model=Task)
async def create_task(payload: TaskCreate) -> Task:
    task = store.create_task(payload)
    await events.publish("task.created", task.model_dump())
    return task


@router.get("/{task_id}", response_model=Task)
async def get_task(task_id: str) -> Task:
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=Task)
async def update_task(task_id: str, payload: TaskUpdate) -> Task:
    task = store.update_task(task_id, payload)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await events.publish("task.updated", task.model_dump())
    return task


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str) -> None:
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    deleted = store.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    await events.publish("task.deleted", {"id": task_id})


@router.get("/{task_id}/messages", response_model=list[TaskMessage])
async def list_task_messages(task_id: str) -> list[TaskMessage]:
    if store.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return store.list_messages(task_id)


@router.post("/{task_id}/messages", response_model=TaskMessage)
async def create_task_message(task_id: str, payload: MessageCreate) -> TaskMessage:
    if store.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    message = TaskMessage(
        id=make_id("msg"),
        task_id=task_id,
        sender_type=payload.sender_type,
        sender_id=payload.sender_id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        message_type=payload.message_type,
        content=payload.content,
        artifact_id=payload.artifact_id,
        created_at=now_ms(),
    )
    store.add_message(task_id, message)
    await events.publish("task.message_created", message.model_dump())
    return message


@router.post("/{task_id}/assign", response_model=Task)
async def assign_task(task_id: str, payload: AssignRequest) -> Task:
    task = store.assign_task(task_id, payload)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await events.publish("task.updated", task.model_dump())
    return task


@router.post("/{task_id}/handoff", response_model=TaskMessage)
async def handoff_task(task_id: str, payload: HandoffRequest) -> TaskMessage:
    if store.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    message = store.create_handoff_message(task_id, payload)
    task = store.get_task(task_id)
    await events.publish("task.message_created", message.model_dump())
    if task is not None:
        await events.publish("task.updated", task.model_dump())
    return message


@router.get("/{task_id}/summary", response_model=TaskContextSummary | None)
async def get_task_summary(task_id: str) -> TaskContextSummary | None:
    if store.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return store.get_task_context_summary(task_id)


@router.post("/{task_id}/summary/rebuild", response_model=TaskContextSummary | None)
async def rebuild_task_summary(task_id: str) -> TaskContextSummary | None:
    if store.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return store.rebuild_task_context_summary(task_id)


@router.get("/{task_id}/workspace", response_model=Workspace)
async def get_task_workspace(task_id: str) -> Workspace:
    if store.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    workspace = store.get_workspace_by_task(task_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.post("/{task_id}/workspace", response_model=Workspace)
async def create_task_workspace(task_id: str) -> Workspace:
    if store.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        return await workspace_manager.create_for_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.deps import events, runner, store
from app.models import Run, RunCreate, RunEvent, RunEventCreate, RunStatus

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=list[Run])
async def list_runs() -> list[Run]:
    return store.list_runs()


@router.post("", response_model=Run)
async def create_run(payload: RunCreate) -> Run:
    if store.get_task(payload.task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    run = store.create_run(payload)
    await events.publish("run.created", run.model_dump())
    return run


@router.get("/{run_id}", response_model=Run)
async def get_run(run_id: str) -> Run:
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{run_id}/events", response_model=list[RunEvent])
async def list_run_events(run_id: str) -> list[RunEvent]:
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return store.list_run_events(run_id)


@router.post("/{run_id}/events", response_model=RunEvent)
async def create_run_event(run_id: str, payload: RunEventCreate) -> RunEvent:
    event = store.add_run_event(run_id, payload)
    if event is None:
        raise HTTPException(status_code=404, detail="Run not found")
    await events.publish("run.event", event.model_dump())
    return event


@router.post("/{run_id}/complete", response_model=Run)
async def complete_run(run_id: str) -> Run:
    run = store.update_run_status(run_id, RunStatus.COMPLETED, exit_code=0)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    await events.publish("run.updated", run.model_dump())
    return run


@router.post("/{run_id}/fail", response_model=Run)
async def fail_run(run_id: str, exit_code: int = 1) -> Run:
    run = store.update_run_status(run_id, RunStatus.FAILED, exit_code=exit_code)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    await events.publish("run.updated", run.model_dump())
    return run


@router.post("/{run_id}/stop", response_model=Run)
async def stop_run(run_id: str) -> Run:
    run = await runner.stop_run(run_id)
    if run is None:
        run = store.update_run_status(run_id, RunStatus.STOPPED)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run

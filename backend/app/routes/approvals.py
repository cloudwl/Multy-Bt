from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.deps import events, store
from app.models import Approval, ApprovalCreate, ApprovalStatus

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=list[Approval])
async def list_approvals() -> list[Approval]:
    return store.list_approvals()


@router.post("", response_model=Approval)
async def create_approval(payload: ApprovalCreate) -> Approval:
    approval = store.create_approval(payload)
    await events.publish("approval.created", approval.model_dump())
    return approval


@router.post("/{approval_id}/approve", response_model=Approval)
async def approve(approval_id: str, resolved_by: str = Query(...)) -> Approval:
    approval = store.resolve_approval(approval_id, ApprovalStatus.APPROVED, resolved_by)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    await events.publish("approval.updated", approval.model_dump())
    return approval


@router.post("/{approval_id}/reject", response_model=Approval)
async def reject(approval_id: str, resolved_by: str = Query(...)) -> Approval:
    approval = store.resolve_approval(approval_id, ApprovalStatus.REJECTED, resolved_by)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    await events.publish("approval.updated", approval.model_dump())
    return approval

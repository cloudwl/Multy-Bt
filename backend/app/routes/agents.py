from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.deps import events, store
from app.models import Agent, AgentRegister, AgentStatusUpdate

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[Agent])
async def list_agents() -> list[Agent]:
    return store.list_agents()


@router.post("/register", response_model=Agent)
async def register_agent(payload: AgentRegister) -> Agent:
    agent = store.register_agent(payload)
    await events.publish("agent.registered", agent.model_dump())
    return agent


@router.patch("/{agent_id}/status", response_model=Agent)
async def update_agent_status(agent_id: str, payload: AgentStatusUpdate) -> Agent:
    agent = store.update_agent_status(agent_id, payload)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    await events.publish("agent.updated", agent.model_dump())
    return agent

# Architecture

## Overview

`Multy-Bt` should be built as a local orchestration service with a web UI.

Core components:

1. `Coordinator`
2. `Task Store`
3. `Event Bus`
4. `Workspace Manager`
5. `Agent Adapters`
6. `Web UI`

## Component Model

### Coordinator

Responsibilities:

- create tasks
- assign tasks
- route messages
- enforce approval gates
- maintain run state

The coordinator is the control plane.

### Task Store

Recommended V1 choice:

- `SQLite`

Tables should cover:

- tasks
- messages
- agents
- runs
- workspaces
- locks
- artifacts

### Event Bus

Recommended V1 choice:

- in-process event dispatcher
- WebSocket fan-out to clients

The system needs streaming updates for:

- run output
- progress
- handoff
- approval requests
- task status changes

### Workspace Manager

Responsibilities:

- create task workspace
- create task branch or `git worktree`
- track workspace path
- clean up archived workspaces

V1 should prefer `git worktree` when repository-backed.

### Agent Adapters

Each adapter should translate between:

- `Multy-Bt` task protocol
- specific CLI invocation format

V1 adapters:

- `codex_adapter`
- `claude_code_adapter`

Adapter responsibilities:

- construct prompt payload
- launch process
- stream stdout/stderr
- detect completion / failure
- emit structured events

### Web UI

The UI should expose:

- task board
- task detail view
- live run output
- shared channel
- agent status
- workspace info
- approval actions

## Data Flow

1. Human creates a task
2. Coordinator assigns agent
3. Workspace manager creates task workspace
4. Adapter launches CLI in that workspace
5. Adapter streams output into event bus
6. Web UI displays live state
7. Agent can emit question / handoff / result
8. Human or coordinator decides next step

## Safety Rules

- No direct agent-to-agent uncontrolled communication
- All communication passes through coordinator
- Risky operations require explicit approval
- Workspace ownership must be visible
- File or task lock conflicts must be surfaced

## Recommended V1 Stack

- Backend: `FastAPI`
- Frontend: `React`
- Realtime: `WebSocket`
- Storage: `SQLite`
- Process execution: local subprocess management
- Workspace isolation: `git worktree`

This stack is chosen for speed of iteration, not ideological purity.

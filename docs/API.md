# API

## Overview

V1 backend should expose:

- REST API for durable state operations
- WebSocket for live event streaming

Base assumption:

- local-first deployment
- LAN access allowed
- one backend process coordinates human UI and local agent adapters

## REST

Base path:

- `/api/v1`

### Health

`GET /api/v1/health`

Response:

```json
{
  "status": "ok",
  "service": "multy-bt"
}
```

### Tasks

`GET /api/v1/tasks`

Query params:

- `status`
- `assigned_agent_id`

`POST /api/v1/tasks`

Request:

```json
{
  "title": "Fix macOS checkbox visuals",
  "summary": "Align macOS checkbox rendering with Windows clarity",
  "created_by": "cloudwl",
  "assigned_agent_id": "codex_local",
  "repo_path": "/Users/cloudwl/quantumearth",
  "priority": "normal"
}
```

`GET /api/v1/tasks/{task_id}`

`PATCH /api/v1/tasks/{task_id}`

Allowed updates:

- `title`
- `summary`
- `status`
- `assigned_agent_id`
- `priority`
- `workspace_id`
- `branch_name`

`POST /api/v1/tasks/{task_id}/messages`

Request:

```json
{
  "sender_type": "human",
  "sender_id": "cloudwl",
  "target_type": "agent",
  "target_id": "codex_local",
  "message_type": "instruction",
  "content": "Investigate the layout issue in mixed Chinese and English text."
}
```

`GET /api/v1/tasks/{task_id}/messages`

`GET /api/v1/tasks/{task_id}/workspace`

`POST /api/v1/tasks/{task_id}/workspace`

Behavior:

- creates an isolated task workspace if one does not already exist
- for git repos, creates a `git worktree`
- for non-git paths, creates a dedicated directory workspace
- updates the task with `workspace_id` and `branch_name` when applicable

`POST /api/v1/tasks/{task_id}/assign`

Request:

```json
{
  "agent_id": "claude_local"
}
```

`POST /api/v1/tasks/{task_id}/handoff`

Request:

```json
{
  "from_agent_id": "codex_local",
  "to_agent_id": "claude_local",
  "content": "Code change complete. Please review architecture impact."
}
```

### Agents

`GET /api/v1/agents`

`POST /api/v1/agents/register`

Request:

```json
{
  "id": "codex_local",
  "name": "Codex Local",
  "kind": "codex",
  "transport": "cli",
  "host": "cloudwldeMacBook-Air"
}
```

`PATCH /api/v1/agents/{agent_id}/status`

### Workspaces

`GET /api/v1/workspaces`

`GET /api/v1/workspaces/{workspace_id}`

`POST /api/v1/workspaces`

Request:

```json
{
  "task_id": "task_01"
}
```

### Runs

`GET /api/v1/runs`

`POST /api/v1/runs`

Request:

```json
{
  "task_id": "task_01",
  "agent_id": "codex_local",
  "command_line": "codex run",
  "cwd": "/Users/cloudwl/worktrees/task_01"
}
```

`GET /api/v1/runs/{run_id}`

`GET /api/v1/runs/{run_id}/events`

`POST /api/v1/runs/{run_id}/events`

`POST /api/v1/runs/{run_id}/complete`

`POST /api/v1/runs/{run_id}/fail`

`POST /api/v1/runs/{run_id}/stop`

### Approvals

`GET /api/v1/approvals`

`POST /api/v1/approvals`

`POST /api/v1/approvals/{approval_id}/approve`

`POST /api/v1/approvals/{approval_id}/reject`

### Adapters

`POST /api/v1/adapters/codex/launch`

Request:

```json
{
  "task_id": "task_01",
  "prompt": "Investigate the current repository and summarize the top two risks.",
  "cwd": "/Users/cloudwl/quantumearth",
  "sandbox": "workspace-write",
  "full_auto": true,
  "skip_git_repo_check": true
}
```

Behavior:

- creates a run
- if `cwd` is omitted, resolves the task workspace automatically
- launches local `codex exec --json`
- streams stdout / stderr into `run_events`
- keeps the run visible through `/api/v1/runs/{run_id}`

`POST /api/v1/adapters/claude/launch`

Request:

```json
{
  "task_id": "task_02",
  "prompt": "Review the current backend structure and identify two design risks.",
  "cwd": "/Users/cloudwl/Multy-Bt/backend",
  "permission_mode": "default",
  "output_format": "stream-json",
  "print_mode": true,
  "no_session_persistence": true
}
```

Behavior:

- creates a run
- if `cwd` is omitted, resolves the task workspace automatically
- launches local `claude --print --output-format stream-json`
- streams stdout / stderr into `run_events`
- keeps the run visible through `/api/v1/runs/{run_id}`

## WebSocket

Endpoint:

- `/ws`

The server pushes structured events to all subscribed clients.

## WebSocket Event Envelope

```json
{
  "event": "task.updated",
  "payload": {
    "id": "task_01",
    "status": "review"
  },
  "timestamp": 1741410000000
}
```

## Initial Event Types

- `task.created`
- `task.updated`
- `task.message_created`
- `agent.registered`
- `agent.updated`
- `run.created`
- `run.updated`
- `run.event`
- `workspace.created`
- `approval.created`
- `approval.updated`

## Adapter Contract

An agent adapter should use the same public API as other clients.

Minimum adapter flow:

1. register agent
2. poll or subscribe for assigned work
3. create run
4. emit run events
5. emit task messages
6. resolve run

This keeps adapters replaceable and observable.

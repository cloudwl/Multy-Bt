# Data Model

## Overview

V1 should use `SQLite`.

The schema should be small, explicit, and easy to inspect by hand.

## Tables

### tasks

Purpose:

- the primary unit of work

Fields:

- `id`: text primary key
- `title`: text not null
- `summary`: text not null default `""`
- `status`: text not null
- `priority`: text not null default `"normal"`
- `created_by`: text not null
- `assigned_agent_id`: text null
- `workspace_id`: text null
- `repo_path`: text null
- `branch_name`: text null
- `created_at`: integer not null
- `updated_at`: integer not null
- `closed_at`: integer null

Allowed `status`:

- `todo`
- `in_progress`
- `blocked`
- `review`
- `done`
- `cancelled`

### messages

Purpose:

- structured communication log for a task

Fields:

- `id`: text primary key
- `task_id`: text not null
- `sender_type`: text not null
- `sender_id`: text not null
- `target_type`: text null
- `target_id`: text null
- `message_type`: text not null
- `content`: text not null
- `artifact_id`: text null
- `created_at`: integer not null

Allowed `sender_type`:

- `human`
- `agent`
- `system`

Allowed `target_type`:

- `human`
- `agent`
- `broadcast`

Allowed `message_type`:

- `instruction`
- `question`
- `proposal`
- `decision`
- `progress`
- `artifact`
- `handoff`
- `error`

### agents

Purpose:

- registered local agents

Fields:

- `id`: text primary key
- `name`: text not null
- `kind`: text not null
- `transport`: text not null
- `status`: text not null
- `host`: text not null
- `working_dir`: text null
- `last_seen_at`: integer not null
- `created_at`: integer not null

Allowed `kind`:

- `codex`
- `claude_code`
- `custom`

Allowed `status`:

- `idle`
- `busy`
- `offline`
- `error`

### agent_sessions

Purpose:

- persisted conversation/session identity per task and agent

Fields:

- `task_id`: text not null
- `agent_id`: text not null
- `session_id`: text not null
- `cwd`: text null
- `created_at`: integer not null
- `updated_at`: integer not null

Primary key:

- `(task_id, agent_id)`

### runs

Purpose:

- one concrete execution session of one agent on one task

Fields:

- `id`: text primary key
- `task_id`: text not null
- `agent_id`: text not null
- `status`: text not null
- `command_line`: text not null
- `cwd`: text not null
- `pid`: integer null
- `started_at`: integer not null
- `ended_at`: integer null
- `exit_code`: integer null

Allowed `status`:

- `queued`
- `running`
- `waiting_approval`
- `completed`
- `failed`
- `stopped`

### run_events

Purpose:

- streaming event log for each run

Fields:

- `id`: text primary key
- `run_id`: text not null
- `event_type`: text not null
- `seq`: integer not null
- `payload_json`: text not null
- `created_at`: integer not null

Allowed `event_type`:

- `stdout`
- `stderr`
- `status`
- `approval_requested`
- `approval_resolved`
- `result`
- `heartbeat`

### workspaces

Purpose:

- isolated working directory for a task

Fields:

- `id`: text primary key
- `task_id`: text not null
- `repo_path`: text null
- `workspace_path`: text not null
- `branch_name`: text null
- `worktree_path`: text null
- `status`: text not null
- `created_at`: integer not null
- `updated_at`: integer not null

Allowed `status`:

- `created`
- `active`
- `archived`
- `deleted`

### locks

Purpose:

- visible ownership of task, workspace, or file-level coordination

Fields:

- `id`: text primary key
- `scope_type`: text not null
- `scope_key`: text not null
- `owner_type`: text not null
- `owner_id`: text not null
- `task_id`: text null
- `created_at`: integer not null
- `expires_at`: integer null

Allowed `scope_type`:

- `task`
- `workspace`
- `file`

### artifacts

Purpose:

- explicit outputs produced by humans or agents

Fields:

- `id`: text primary key
- `task_id`: text not null
- `run_id`: text null
- `artifact_type`: text not null
- `title`: text not null
- `content_text`: text null
- `path`: text null
- `metadata_json`: text null
- `created_at`: integer not null

Allowed `artifact_type`:

- `summary`
- `patch`
- `diff`
- `file`
- `decision`
- `note`

### approvals

Purpose:

- explicit human gate for risky actions

Fields:

- `id`: text primary key
- `task_id`: text not null
- `run_id`: text not null
- `requested_by_agent_id`: text not null
- `action_type`: text not null
- `reason`: text not null
- `payload_json`: text not null
- `status`: text not null
- `resolved_by`: text null
- `resolved_at`: integer null
- `created_at`: integer not null

Allowed `status`:

- `pending`
- `approved`
- `rejected`

## Indexes

V1 should add indexes for:

- `messages(task_id, created_at)`
- `runs(task_id, started_at)`
- `run_events(run_id, seq)`
- `locks(scope_type, scope_key)`
- `artifacts(task_id, created_at)`
- `approvals(task_id, status)`

## Design Notes

- ids should be human-readable enough for debugging, for example `task_xxx`, `msg_xxx`
- timestamps should be unix milliseconds
- enums can remain plain text in V1
- `payload_json` should be JSON strings to keep the initial schema flexible

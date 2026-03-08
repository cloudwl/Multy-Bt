# Message Protocol

## Goal

All participants should communicate through one structured protocol.

Participants:

- human
- agent
- coordinator

The protocol must support:

- direct instruction
- question and answer
- proposal and decision
- handoff
- progress updates
- artifacts
- approval requests

## Envelope

Each message should have this common shape:

```json
{
  "id": "msg_01",
  "task_id": "task_01",
  "sender": {
    "type": "agent",
    "id": "codex_local"
  },
  "target": {
    "type": "human",
    "id": "cloudwl"
  },
  "type": "question",
  "content": "Should I update Cargo.lock in this task?",
  "artifact_id": null,
  "created_at": 1741410000000
}
```

## Message Types

### instruction

Used when the human or coordinator gives executable guidance.

Example:

```json
{
  "type": "instruction",
  "content": "Investigate macOS build failure in this repo and report root cause."
}
```

### question

Used when an agent needs clarification or approval-related input.

Example:

```json
{
  "type": "question",
  "content": "The repo has unrelated dirty files. Should I continue without touching them?"
}
```

### proposal

Used when an agent suggests a plan or tradeoff.

Example:

```json
{
  "type": "proposal",
  "content": "I recommend adding a platform abstraction instead of branching UI logic in-place."
}
```

### decision

Used to record a final choice by the human or coordinator.

Example:

```json
{
  "type": "decision",
  "content": "Proceed with platform abstraction. Do not change Windows behavior."
}
```

### progress

Used for concise execution updates.

Example:

```json
{
  "type": "progress",
  "content": "Read the repo structure and identified 2 likely macOS blockers."
}
```

### artifact

Used when a message points to a concrete output.

Example:

```json
{
  "type": "artifact",
  "content": "Created initial schema draft.",
  "artifact_id": "artifact_schema_v1"
}
```

### handoff

Used when work transfers between agents.

Example:

```json
{
  "type": "handoff",
  "content": "Handing off to Claude for architectural review. Code changes are in workspace wt_task_07."
}
```

### error

Used when work fails or is blocked.

Example:

```json
{
  "type": "error",
  "content": "Git fetch failed because the upstream branch is missing in remote-tracking refs."
}
```

## Run Events

Run events are lower-level than task messages.

They describe process execution:

- `stdout`
- `stderr`
- `status`
- `approval_requested`
- `approval_resolved`
- `result`
- `heartbeat`

Example:

```json
{
  "id": "run_event_01",
  "run_id": "run_01",
  "event_type": "stdout",
  "seq": 14,
  "payload": {
    "text": "Compiling quantum_earth v0.1.0"
  },
  "created_at": 1741410000200
}
```

## Approval Request Shape

When an agent needs approval, the coordinator should surface:

```json
{
  "id": "approval_01",
  "task_id": "task_01",
  "run_id": "run_01",
  "requested_by_agent_id": "codex_local",
  "action_type": "git_push",
  "reason": "Changes are validated and ready to publish.",
  "payload": {
    "branch": "Rust4Mac",
    "remote": "origin"
  },
  "status": "pending"
}
```

## Handoff Contract

Every handoff should include:

- what was done
- what remains
- where the workspace is
- what risks are known
- what exact files were touched

Suggested content template:

```text
Completed:
- fixed GitHub OAuth client_secret flow
- added remove-repo action

Remaining:
- verify checkbox visuals on macOS

Workspace:
- /path/to/worktree

Touched files:
- src/auth/oauth.rs
- src/app/ui/main_panel.rs

Risks:
- visual tuning may still need adjustment on high-DPI macOS displays
```

## Rules

- agents do not communicate out-of-band
- free-form text is allowed, but every message must have a defined `type`
- important state transitions should create both:
  - a run event
  - a task message
- handoff messages are mandatory when switching agents on one task

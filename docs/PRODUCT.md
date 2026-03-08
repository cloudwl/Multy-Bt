# Product

## Positioning

`Multy-Bt` is a transparent collaboration system for one human and multiple local AI agents.

The problem it solves:

- existing multi-agent products are mostly API-first
- existing CLI agents cannot naturally cooperate with each other
- humans cannot see the real coordination process
- context transfer between agents is manual and fragile

## Target User

Primary user:

- an advanced individual developer using multiple local coding agents on one or more personal machines

Typical setup:

- `Codex CLI`
- `Claude Code CLI`
- multiple repositories
- local subscriptions instead of API billing

## Core Value

`Multy-Bt` should make multi-agent work:

- visible
- interruptible
- reviewable
- reproducible

## Product Requirements

### 1. Shared Task System

Every meaningful action belongs to a task.

A task should have:

- id
- title
- status
- owner
- target agent
- workspace
- summary
- artifacts

### 2. Shared Structured Channel

The system should not rely on free-form chat only.

Message types should include:

- `instruction`
- `question`
- `proposal`
- `decision`
- `progress`
- `artifact`
- `handoff`
- `error`

### 3. Agent Adapters

The system should wrap local CLIs instead of replacing them.

Initial adapters:

- `Codex`
- `Claude Code`

Each adapter should support:

- receive task
- receive scoped context
- run command
- stream output
- emit structured events

### 4. Human-in-the-Loop

The operator must be able to:

- inspect all task state
- inspect all handoffs
- approve or reject risky actions
- redirect tasks between agents
- pause or stop an agent run

### 5. Workspace Isolation

Each task should run in a separate workspace, ideally via `git worktree`.

This avoids:

- file overwrite conflicts
- branch confusion
- hidden context mixing

## Non-Goals For V1

- fully autonomous agent negotiation
- cloud dependency as a hard requirement
- advanced billing / team org system
- complex permissions model

## Success Criteria For V1

Version 1 is successful if:

- one human can coordinate `Codex CLI` and `Claude Code CLI` in one visible system
- tasks can be assigned without copy-pasting between terminals
- each task has isolated workspace state
- handoff and progress are visible in real time
- the human can intervene at any point

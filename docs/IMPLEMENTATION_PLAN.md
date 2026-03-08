# Implementation Plan

## Phase 1

Goal:

- define backend contracts before coding

Deliverables:

- data model
- message protocol
- approval model

## Phase 2

Goal:

- backend skeleton

Deliverables:

- `FastAPI` app
- SQLite bootstrap
- task CRUD
- websocket event stream

## Phase 3

Goal:

- first agent integration

Deliverables:

- `Codex` adapter
- local process runner
- streamed run output

## Phase 4

Goal:

- second agent integration

Deliverables:

- `Claude Code` adapter
- shared task assignment flow
- handoff flow

## Phase 5

Goal:

- workspace isolation

Deliverables:

- `git worktree` manager
- task-to-workspace mapping
- cleanup commands

## Phase 6

Goal:

- usable web UI

Deliverables:

- task board
- task detail page
- live output pane
- approval pane

## Immediate Next Step

The next correct engineering step is:

- define the concrete backend API routes and websocket event schema

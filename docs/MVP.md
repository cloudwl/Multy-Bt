# MVP

## Objective

Deliver a usable first version that replaces manual relay work between:

- the human operator
- `Codex CLI`
- `Claude Code CLI`

## Must Have

### 1. Task Board

Statuses:

- `todo`
- `in_progress`
- `blocked`
- `review`
- `done`

### 2. Task Detail Page

A task page should show:

- title
- summary
- assigned agent
- workspace path
- live output
- message history
- result artifacts

### 3. Shared Structured Channel

Each message should include:

- `task_id`
- `sender`
- `target`
- `type`
- `content`
- `timestamp`

### 4. Agent Runner

Support:

- start `Codex CLI`
- start `Claude Code CLI`
- stream output
- stop run
- mark completion

### 5. Workspace Isolation

For repo tasks:

- create per-task `git worktree`
- record branch and path

### 6. Approval Gate

Require manual approval for:

- destructive commands
- git push
- branch delete
- cleanup of active workspace

## Nice To Have

- task templates
- agent capability tags
- result summary generation
- file lock view
- lightweight diff preview

## Not In MVP

- cross-machine sync
- mobile client
- desktop control
- full memory system
- automatic agent-to-agent debate

## Suggested Build Order

1. backend service skeleton
2. sqlite schema
3. task CRUD
4. websocket event stream
5. codex adapter
6. claude adapter
7. workspace manager
8. web UI board and task detail
9. approval flow
10. cleanup and persistence

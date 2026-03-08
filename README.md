# Multy-Bt

`Multy-Bt` is a local-first multi-agent collaboration platform for humans and CLI agents.

## Goal

Build a LAN-accessible coordination layer where:

- a human operator
- `Codex CLI`
- `Claude Code CLI`
- future local agents

can work inside one visible system instead of relying on manual copy-paste.

## Principles

- `CLI first`: reuse existing subscribed CLI agents instead of forcing API-only orchestration
- `Human visible`: task assignment, handoff, reasoning summary, and results must be visible
- `Human override`: important actions stay under explicit human control
- `Artifact based`: collaboration is centered on tasks, diffs, decisions, questions, and results
- `Workspace isolated`: each task should run in an isolated workspace or `git worktree`

## What This Is Not

- Not a black-box autonomous agent swarm
- Not an API-only LLM router
- Not just a chat room
- Not limited to GitHub PR workflow

## First Scope

The first version focuses on software development collaboration:

- shared task board
- shared structured channel
- local CLI agent adapters
- workspace / worktree isolation
- visible handoff and review flow
- minimal web control surface for tasks, workspaces, runs, agents, and live events

Later versions can extend to:

- desktop automation
- personal memory
- device coordination
- Feishu / IM integration

## Docs

- [Product](./docs/PRODUCT.md)
- [Architecture](./docs/ARCHITECTURE.md)
- [MVP](./docs/MVP.md)

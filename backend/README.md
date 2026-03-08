# Backend

## Run

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```

Windows PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000/
```

## Current State

This is a first executable skeleton:

- REST routes exist
- WebSocket event stream exists
- static frontend exists at `/`
- SQLite persistence is wired
- database path defaults to `backend/data/multy_bt.sqlite3`
- set `MULTY_BT_DB_PATH` to override the database location
- workspace manager is wired
- task workspaces default to `backend/data/workspaces`
- set `MULTY_BT_WORKSPACES_ROOT` to override the workspace root
- `Codex` adapter launch route exists
- `codex exec --json` output is persisted as run events
- `Claude Code` adapter launch route exists
- `claude --print --output-format stream-json` output is persisted as run events
- adapter launches auto-resolve an isolated task workspace when `cwd` is omitted

Current limitation:

- agent execution still depends on local CLI auth / network state
- process supervision is basic; no retry or resume logic yet

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import TypeVar

from app.models import (
    Agent,
    AgentRegister,
    AgentSession,
    AgentStatus,
    AgentStatusUpdate,
    Approval,
    ApprovalCreate,
    ApprovalStatus,
    AssignRequest,
    HandoffRequest,
    MessageType,
    Run,
    RunCreate,
    RunEvent,
    RunEventCreate,
    RunStatus,
    SenderType,
    TargetType,
    Task,
    TaskContextSummary,
    TaskCreate,
    TaskMessage,
    TaskStatus,
    TaskUpdate,
    Workspace,
    WorkspaceKind,
    WorkspaceStatus,
)

ModelT = TypeVar("ModelT", Task, TaskMessage, Agent, Run, RunEvent, Approval, Workspace)

SUMMARY_RECENT_CONTEXT_LIMIT = 12
SUMMARY_RAW_MESSAGE_LIMIT = 6


def now_ms() -> int:
    return int(time.time() * 1000)


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def default_db_path() -> Path:
    env_path = os.environ.get("MULTY_BT_DB_PATH")
    if env_path:
        return Path(env_path).expanduser()
    return Path(__file__).resolve().parents[2] / "data" / "multy_bt.sqlite3"


class SQLiteStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    assigned_agent_id TEXT,
                    workspace_id TEXT,
                    repo_path TEXT,
                    branch_name TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    sender_type TEXT NOT NULL,
                    sender_id TEXT NOT NULL,
                    target_type TEXT,
                    target_id TEXT,
                    message_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    artifact_id TEXT,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    transport TEXT NOT NULL,
                    status TEXT NOT NULL,
                    host TEXT NOT NULL,
                    working_dir TEXT,
                    last_seen_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_sessions (
                    task_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    cwd TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (task_id, agent_id),
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    command_line TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    pid INTEGER,
                    started_at INTEGER NOT NULL,
                    ended_at INTEGER,
                    exit_code INTEGER,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS run_events (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    requested_by_agent_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    resolved_by TEXT,
                    resolved_at INTEGER,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL UNIQUE,
                    repo_path TEXT,
                    workspace_path TEXT NOT NULL,
                    branch_name TEXT,
                    worktree_path TEXT,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS task_context_summaries (
                    task_id TEXT PRIMARY KEY,
                    summary_text TEXT NOT NULL,
                    source_message_count INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_messages_task ON messages(task_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_agent_sessions_task ON agent_sessions(task_id, agent_id);
                CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id, started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_run_events_run ON run_events(run_id, seq);
                CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_workspaces_status ON workspaces(status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_task_context_summaries_updated ON task_context_summaries(updated_at DESC);
                """
            )

    def _model_from_row(self, model_type: type[ModelT], row: sqlite3.Row | None) -> ModelT | None:
        if row is None:
            return None
        data = dict(row)
        if "payload_json" in data:
            data["payload"] = json.loads(data.pop("payload_json"))
        return model_type(**data)

    def list_tasks(self, status: TaskStatus | None = None) -> list[Task]:
        with self._lock:
            if status is None:
                rows = self._conn.execute(
                    "SELECT * FROM tasks ORDER BY updated_at DESC"
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY updated_at DESC",
                    (status.value,),
                ).fetchall()
        return [Task(**dict(row)) for row in rows]

    def list_workspaces(self) -> list[Workspace]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM workspaces ORDER BY updated_at DESC"
            ).fetchall()
        return [Workspace(**dict(row)) for row in rows]

    def create_task(self, payload: TaskCreate) -> Task:
        timestamp = now_ms()
        task = Task(
            id=make_id("task"),
            title=payload.title,
            summary=payload.summary,
            status=TaskStatus.TODO,
            priority=payload.priority,
            created_by=payload.created_by,
            assigned_agent_id=payload.assigned_agent_id,
            repo_path=payload.repo_path,
            created_at=timestamp,
            updated_at=timestamp,
        )
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO tasks (
                    id, title, summary, status, priority, created_by,
                    assigned_agent_id, workspace_id, repo_path, branch_name,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.title,
                    task.summary,
                    task.status.value,
                    task.priority.value,
                    task.created_by,
                    task.assigned_agent_id,
                    task.workspace_id,
                    task.repo_path,
                    task.branch_name,
                    task.created_at,
                    task.updated_at,
                ),
            )
        return task

    def delete_task(self, task_id: str) -> bool:
        with self._lock, self._conn:
            cursor = self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return cursor.rowcount > 0

    def upsert_workspace(
        self,
        *,
        task_id: str,
        repo_path: str | None,
        workspace_path: str,
        branch_name: str | None,
        worktree_path: str | None,
        kind: WorkspaceKind,
        status: WorkspaceStatus,
    ) -> Workspace:
        existing = self.get_workspace_by_task(task_id)
        timestamp = now_ms()
        workspace = Workspace(
            id=existing.id if existing else make_id("workspace"),
            task_id=task_id,
            repo_path=repo_path,
            workspace_path=workspace_path,
            branch_name=branch_name,
            worktree_path=worktree_path,
            kind=kind,
            status=status,
            created_at=existing.created_at if existing else timestamp,
            updated_at=timestamp,
        )
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO workspaces (
                    id, task_id, repo_path, workspace_path, branch_name, worktree_path,
                    kind, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    repo_path = excluded.repo_path,
                    workspace_path = excluded.workspace_path,
                    branch_name = excluded.branch_name,
                    worktree_path = excluded.worktree_path,
                    kind = excluded.kind,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    workspace.id,
                    workspace.task_id,
                    workspace.repo_path,
                    workspace.workspace_path,
                    workspace.branch_name,
                    workspace.worktree_path,
                    workspace.kind.value,
                    workspace.status.value,
                    workspace.created_at,
                    workspace.updated_at,
                ),
            )
        return workspace

    def get_task(self, task_id: str) -> Task | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._model_from_row(Task, row)

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
            ).fetchone()
        return self._model_from_row(Workspace, row)

    def get_workspace_by_task(self, task_id: str) -> Workspace | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM workspaces WHERE task_id = ?", (task_id,)
            ).fetchone()
        return self._model_from_row(Workspace, row)

    def update_task(self, task_id: str, payload: TaskUpdate) -> Task | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        data = task.model_dump()
        for key, value in payload.model_dump(exclude_unset=True).items():
            data[key] = value
        data["updated_at"] = now_ms()
        updated = Task(**data)
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE tasks
                SET title = ?, summary = ?, status = ?, priority = ?, created_by = ?,
                    assigned_agent_id = ?, workspace_id = ?, repo_path = ?, branch_name = ?,
                    created_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    updated.title,
                    updated.summary,
                    updated.status.value,
                    updated.priority.value,
                    updated.created_by,
                    updated.assigned_agent_id,
                    updated.workspace_id,
                    updated.repo_path,
                    updated.branch_name,
                    updated.created_at,
                    updated.updated_at,
                    updated.id,
                ),
            )
        return updated

    def assign_task(self, task_id: str, payload: AssignRequest) -> Task | None:
        return self.update_task(task_id, TaskUpdate(assigned_agent_id=payload.agent_id))

    def add_message(self, task_id: str, payload: TaskMessage) -> TaskMessage:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO messages (
                    id, task_id, sender_type, sender_id, target_type, target_id,
                    message_type, content, artifact_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.id,
                    payload.task_id,
                    payload.sender_type.value,
                    payload.sender_id,
                    payload.target_type.value if payload.target_type else None,
                    payload.target_id,
                    payload.message_type.value,
                    payload.content,
                    payload.artifact_id,
                    payload.created_at,
                ),
            )
            self._conn.execute(
                "UPDATE tasks SET updated_at = ? WHERE id = ?", (now_ms(), task_id)
            )
            self._refresh_task_context_summary_locked(task_id)
        return payload

    def list_messages(self, task_id: str) -> list[TaskMessage]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE task_id = ? ORDER BY created_at ASC",
                (task_id,),
            ).fetchall()
        return [TaskMessage(**dict(row)) for row in rows]

    def create_handoff_message(self, task_id: str, payload: HandoffRequest) -> TaskMessage:
        content = payload.content.strip()
        note = (payload.note or "").strip()
        if note:
            content = (
                "Transfer note from human coordinator:\n"
                f"{note}\n\n"
                f"Transferred message from {payload.from_agent_id}:\n"
                f"{content}"
            )
        message = TaskMessage(
            id=make_id("msg"),
            task_id=task_id,
            sender_type=SenderType.AGENT,
            sender_id=payload.from_agent_id,
            target_type=TargetType.AGENT,
            target_id=payload.to_agent_id,
            message_type=MessageType.HANDOFF,
            content=content,
            created_at=now_ms(),
        )
        self.add_message(task_id, message)
        self.assign_task(task_id, AssignRequest(agent_id=payload.to_agent_id))
        return message

    def get_task_context_summary(self, task_id: str) -> TaskContextSummary | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM task_context_summaries WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._model_from_row(TaskContextSummary, row)

    def rebuild_task_context_summary(self, task_id: str) -> TaskContextSummary | None:
        with self._lock, self._conn:
            return self._refresh_task_context_summary_locked(task_id)

    def register_agent(self, payload: AgentRegister) -> Agent:
        timestamp = now_ms()
        with self._lock:
            existing = self._conn.execute(
                "SELECT * FROM agents WHERE id = ?", (payload.id,)
            ).fetchone()
        created_at = existing["created_at"] if existing else timestamp
        agent = Agent(
            id=payload.id,
            name=payload.name,
            kind=payload.kind,
            transport=payload.transport,
            status=AgentStatus.IDLE,
            host=payload.host,
            working_dir=payload.working_dir,
            last_seen_at=timestamp,
            created_at=created_at,
        )
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO agents (
                    id, name, kind, transport, status, host, working_dir, last_seen_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    kind = excluded.kind,
                    transport = excluded.transport,
                    status = excluded.status,
                    host = excluded.host,
                    working_dir = excluded.working_dir,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    agent.id,
                    agent.name,
                    agent.kind.value,
                    agent.transport,
                    agent.status.value,
                    agent.host,
                    agent.working_dir,
                    agent.last_seen_at,
                    agent.created_at,
                ),
            )
        return agent

    def update_agent_status(self, agent_id: str, payload: AgentStatusUpdate) -> Agent | None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE agents SET status = ?, last_seen_at = ? WHERE id = ?",
                (payload.status.value, now_ms(), agent_id),
            )
            row = self._conn.execute(
                "SELECT * FROM agents WHERE id = ?", (agent_id,)
            ).fetchone()
        return self._model_from_row(Agent, row)

    def list_agents(self) -> list[Agent]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM agents ORDER BY id ASC").fetchall()
        return [Agent(**dict(row)) for row in rows]

    def get_agent_session(self, task_id: str, agent_id: str) -> AgentSession | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM agent_sessions WHERE task_id = ? AND agent_id = ?",
                (task_id, agent_id),
            ).fetchone()
        return self._model_from_row(AgentSession, row)

    def upsert_agent_session(
        self, task_id: str, agent_id: str, session_id: str, cwd: str | None = None
    ) -> AgentSession:
        existing = self.get_agent_session(task_id, agent_id)
        timestamp = now_ms()
        session = AgentSession(
            task_id=task_id,
            agent_id=agent_id,
            session_id=session_id,
            cwd=cwd if cwd is not None else (existing.cwd if existing else None),
            created_at=existing.created_at if existing else timestamp,
            updated_at=timestamp,
        )
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO agent_sessions (
                    task_id, agent_id, session_id, cwd, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id, agent_id) DO UPDATE SET
                    session_id = excluded.session_id,
                    cwd = excluded.cwd,
                    updated_at = excluded.updated_at
                """,
                (
                    session.task_id,
                    session.agent_id,
                    session.session_id,
                    session.cwd,
                    session.created_at,
                    session.updated_at,
                ),
            )
        return session

    def _refresh_task_context_summary_locked(
        self, task_id: str
    ) -> TaskContextSummary | None:
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        ).fetchall()
        messages = [TaskMessage(**dict(row)) for row in rows]
        summary_text = self._build_task_summary(messages)
        if summary_text is None:
            self._conn.execute(
                "DELETE FROM task_context_summaries WHERE task_id = ?",
                (task_id,),
            )
            return None

        summary = TaskContextSummary(
            task_id=task_id,
            summary_text=summary_text,
            source_message_count=len(messages),
            updated_at=now_ms(),
        )
        self._conn.execute(
            """
            INSERT INTO task_context_summaries (
                task_id, summary_text, source_message_count, updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                summary_text = excluded.summary_text,
                source_message_count = excluded.source_message_count,
                updated_at = excluded.updated_at
            """,
            (
                summary.task_id,
                summary.summary_text,
                summary.source_message_count,
                summary.updated_at,
            ),
        )
        return summary

    def _build_task_summary(self, messages: list[TaskMessage]) -> str | None:
        if len(messages) <= SUMMARY_RAW_MESSAGE_LIMIT:
            return None

        summary_lines = ["Earlier conversation summary:"]
        older_messages = messages[:-SUMMARY_RAW_MESSAGE_LIMIT]
        for message in older_messages[-SUMMARY_RECENT_CONTEXT_LIMIT:]:
            summary_lines.append(
                f"- {message.sender_type.value}:{message.sender_id} -> "
                f"{self._summary_target_label(message)} "
                f"[{message.message_type.value}] "
                f"{self._truncate_summary_content(message.content)}"
            )
        return "\n".join(summary_lines)

    def _summary_target_label(self, message: TaskMessage) -> str:
        if message.target_type == TargetType.AGENT:
            return message.target_id or "agent"
        if message.target_type == TargetType.HUMAN:
            return message.target_id or "human"
        return "everyone"

    def _truncate_summary_content(self, content: str, limit: int = 160) -> str:
        text = " ".join(content.split())
        if len(text) <= limit:
            return text
        return f"{text[: limit - 1]}..."

    def create_run(self, payload: RunCreate) -> Run:
        run = Run(
            id=make_id("run"),
            task_id=payload.task_id,
            agent_id=payload.agent_id,
            status=RunStatus.QUEUED,
            command_line=payload.command_line,
            cwd=payload.cwd,
            started_at=now_ms(),
        )
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO runs (
                    id, task_id, agent_id, status, command_line, cwd,
                    pid, started_at, ended_at, exit_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.task_id,
                    run.agent_id,
                    run.status.value,
                    run.command_line,
                    run.cwd,
                    run.pid,
                    run.started_at,
                    run.ended_at,
                    run.exit_code,
                ),
            )
        return run

    def get_run(self, run_id: str) -> Run | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return self._model_from_row(Run, row)

    def update_run_status(
        self, run_id: str, status: RunStatus, exit_code: int | None = None
    ) -> Run | None:
        run = self.get_run(run_id)
        if run is None:
            return None
        ended_at = run.ended_at
        new_exit_code = run.exit_code
        if status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.STOPPED}:
            ended_at = now_ms()
            new_exit_code = exit_code
        updated = run.model_copy(
            update={"status": status, "ended_at": ended_at, "exit_code": new_exit_code}
        )
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE runs
                SET task_id = ?, agent_id = ?, status = ?, command_line = ?, cwd = ?,
                    pid = ?, started_at = ?, ended_at = ?, exit_code = ?
                WHERE id = ?
                """,
                (
                    updated.task_id,
                    updated.agent_id,
                    updated.status.value,
                    updated.command_line,
                    updated.cwd,
                    updated.pid,
                    updated.started_at,
                    updated.ended_at,
                    updated.exit_code,
                    updated.id,
                ),
            )
        return updated

    def update_run_pid(self, run_id: str, pid: int | None) -> Run | None:
        run = self.get_run(run_id)
        if run is None:
            return None
        updated = run.model_copy(update={"pid": pid, "status": RunStatus.RUNNING})
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE runs
                SET task_id = ?, agent_id = ?, status = ?, command_line = ?, cwd = ?,
                    pid = ?, started_at = ?, ended_at = ?, exit_code = ?
                WHERE id = ?
                """,
                (
                    updated.task_id,
                    updated.agent_id,
                    updated.status.value,
                    updated.command_line,
                    updated.cwd,
                    updated.pid,
                    updated.started_at,
                    updated.ended_at,
                    updated.exit_code,
                    updated.id,
                ),
            )
        return updated

    def list_runs(self) -> list[Run]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM runs ORDER BY started_at DESC"
            ).fetchall()
        return [Run(**dict(row)) for row in rows]

    def list_run_events(self, run_id: str) -> list[RunEvent]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM run_events WHERE run_id = ? ORDER BY seq ASC",
                (run_id,),
            ).fetchall()
        return [self._model_from_row(RunEvent, row) for row in rows]

    def add_run_event(self, run_id: str, payload: RunEventCreate) -> RunEvent | None:
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
            if exists is None:
                return None
            seq_row = self._conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM run_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            seq = int(seq_row["max_seq"]) + 1
        event = RunEvent(
            id=make_id("run_event"),
            run_id=run_id,
            event_type=payload.event_type,
            seq=seq,
            payload=payload.payload,
            created_at=now_ms(),
        )
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO run_events (id, run_id, event_type, seq, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.run_id,
                    event.event_type.value,
                    event.seq,
                    json.dumps(event.payload, ensure_ascii=True),
                    event.created_at,
                ),
            )
        return event

    def create_approval(self, payload: ApprovalCreate) -> Approval:
        approval = Approval(
            id=make_id("approval"),
            task_id=payload.task_id,
            run_id=payload.run_id,
            requested_by_agent_id=payload.requested_by_agent_id,
            action_type=payload.action_type,
            reason=payload.reason,
            payload=payload.payload,
            status=ApprovalStatus.PENDING,
            created_at=now_ms(),
        )
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO approvals (
                    id, task_id, run_id, requested_by_agent_id, action_type,
                    reason, payload_json, status, resolved_by, resolved_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval.id,
                    approval.task_id,
                    approval.run_id,
                    approval.requested_by_agent_id,
                    approval.action_type,
                    approval.reason,
                    json.dumps(approval.payload, ensure_ascii=True),
                    approval.status.value,
                    approval.resolved_by,
                    approval.resolved_at,
                    approval.created_at,
                ),
            )
        return approval

    def list_approvals(self) -> list[Approval]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM approvals ORDER BY created_at DESC"
            ).fetchall()
        return [self._model_from_row(Approval, row) for row in rows]

    def resolve_approval(
        self, approval_id: str, status: ApprovalStatus, resolved_by: str
    ) -> Approval | None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE approvals
                SET status = ?, resolved_by = ?, resolved_at = ?
                WHERE id = ?
                """,
                (status.value, resolved_by, now_ms(), approval_id),
            )
            row = self._conn.execute(
                "SELECT * FROM approvals WHERE id = ?", (approval_id,)
            ).fetchone()
        return self._model_from_row(Approval, row)

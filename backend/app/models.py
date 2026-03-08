from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEW = "review"
    DONE = "done"
    CANCELLED = "cancelled"


class Priority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class SenderType(str, Enum):
    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


class TargetType(str, Enum):
    HUMAN = "human"
    AGENT = "agent"
    BROADCAST = "broadcast"


class MessageType(str, Enum):
    INSTRUCTION = "instruction"
    QUESTION = "question"
    PROPOSAL = "proposal"
    DECISION = "decision"
    PROGRESS = "progress"
    ARTIFACT = "artifact"
    HANDOFF = "handoff"
    ERROR = "error"


class AgentKind(str, Enum):
    CODEX = "codex"
    CLAUDE_CODE = "claude_code"
    CUSTOM = "custom"


class AgentStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"
    ERROR = "error"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class RunEventType(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"
    STATUS = "status"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RESOLVED = "approval_resolved"
    RESULT = "result"
    HEARTBEAT = "heartbeat"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SandboxMode(str, Enum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    DANGER_FULL_ACCESS = "danger-full-access"


class ClaudePermissionMode(str, Enum):
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    DONT_ASK = "dontAsk"
    PLAN = "plan"
    AUTO = "auto"
    BYPASS_PERMISSIONS = "bypassPermissions"


class WorkspaceStatus(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class WorkspaceKind(str, Enum):
    GIT_WORKTREE = "git_worktree"
    DIRECTORY = "directory"


class TaskCreate(BaseModel):
    title: str
    summary: str = ""
    created_by: str
    assigned_agent_id: str | None = None
    repo_path: str | None = None
    priority: Priority = Priority.NORMAL


class TaskUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None
    status: TaskStatus | None = None
    assigned_agent_id: str | None = None
    priority: Priority | None = None
    workspace_id: str | None = None
    branch_name: str | None = None


class Task(BaseModel):
    id: str
    title: str
    summary: str
    status: TaskStatus
    priority: Priority
    created_by: str
    assigned_agent_id: str | None = None
    repo_path: str | None = None
    branch_name: str | None = None
    workspace_id: str | None = None
    created_at: int
    updated_at: int


class TaskContextSummary(BaseModel):
    task_id: str
    summary_text: str
    source_message_count: int
    updated_at: int


class WorkspaceCreateRequest(BaseModel):
    task_id: str


class Workspace(BaseModel):
    id: str
    task_id: str
    repo_path: str | None = None
    workspace_path: str
    branch_name: str | None = None
    worktree_path: str | None = None
    kind: WorkspaceKind
    status: WorkspaceStatus
    created_at: int
    updated_at: int


class MessageCreate(BaseModel):
    sender_type: SenderType
    sender_id: str
    target_type: TargetType | None = None
    target_id: str | None = None
    message_type: MessageType
    content: str
    artifact_id: str | None = None


class TaskMessage(BaseModel):
    id: str
    task_id: str
    sender_type: SenderType
    sender_id: str
    target_type: TargetType | None = None
    target_id: str | None = None
    message_type: MessageType
    content: str
    artifact_id: str | None = None
    created_at: int


class AgentRegister(BaseModel):
    id: str
    name: str
    kind: AgentKind
    transport: str = "cli"
    host: str
    working_dir: str | None = None


class Agent(BaseModel):
    id: str
    name: str
    kind: AgentKind
    transport: str
    status: AgentStatus
    host: str
    working_dir: str | None = None
    last_seen_at: int
    created_at: int


class AgentStatusUpdate(BaseModel):
    status: AgentStatus


class RunCreate(BaseModel):
    task_id: str
    agent_id: str
    command_line: str
    cwd: str


class Run(BaseModel):
    id: str
    task_id: str
    agent_id: str
    status: RunStatus
    command_line: str
    cwd: str
    pid: int | None = None
    started_at: int
    ended_at: int | None = None
    exit_code: int | None = None


class CodexLaunchRequest(BaseModel):
    task_id: str
    prompt: str
    cwd: str | None = None
    model: str | None = None
    profile: str | None = None
    sandbox: SandboxMode = SandboxMode.WORKSPACE_WRITE
    skip_git_repo_check: bool = True
    full_auto: bool = True


class ClaudeLaunchRequest(BaseModel):
    task_id: str
    prompt: str
    cwd: str | None = None
    model: str | None = None
    permission_mode: ClaudePermissionMode = ClaudePermissionMode.DEFAULT
    output_format: str = "stream-json"
    print_mode: bool = True
    no_session_persistence: bool = True


class RunEventCreate(BaseModel):
    event_type: RunEventType
    payload: dict[str, Any] = Field(default_factory=dict)


class RunEvent(BaseModel):
    id: str
    run_id: str
    event_type: RunEventType
    seq: int
    payload: dict[str, Any]
    created_at: int


class ApprovalCreate(BaseModel):
    task_id: str
    run_id: str
    requested_by_agent_id: str
    action_type: str
    reason: str
    payload: dict[str, Any] = Field(default_factory=dict)


class Approval(BaseModel):
    id: str
    task_id: str
    run_id: str
    requested_by_agent_id: str
    action_type: str
    reason: str
    payload: dict[str, Any]
    status: ApprovalStatus
    resolved_by: str | None = None
    resolved_at: int | None = None
    created_at: int


class AssignRequest(BaseModel):
    agent_id: str


class HandoffRequest(BaseModel):
    from_agent_id: str
    to_agent_id: str
    content: str
    note: str | None = None

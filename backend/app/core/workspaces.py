from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from app.models import TaskUpdate, Workspace, WorkspaceKind, WorkspaceStatus


def default_workspaces_root() -> Path:
    env_path = os.environ.get("MULTY_BT_WORKSPACES_ROOT")
    if env_path:
        return Path(env_path).expanduser()
    return Path(__file__).resolve().parents[2] / "data" / "workspaces"


class WorkspaceManager:
    def __init__(self, store, events, root: Path | None = None) -> None:
        self.store = store
        self.events = events
        self.root = root or default_workspaces_root()
        self.root.mkdir(parents=True, exist_ok=True)

    async def create_for_task(self, task_id: str) -> Workspace:
        task = self.store.get_task(task_id)
        if task is None:
            raise ValueError("Task not found")

        existing = self.store.get_workspace_by_task(task_id)
        if existing is not None and Path(existing.workspace_path).exists():
            return existing

        workspace_dir = self.root / task_id
        repo_path = Path(task.repo_path).expanduser() if task.repo_path else None
        if repo_path is not None:
            repo_path = self._normalize_repo_path(repo_path)
            self._reject_managed_workspace_source(task_id, repo_path)

        if repo_path and self._is_git_repo(repo_path):
            branch_name = self._workspace_branch_name(task_id)
            workspace = self._create_git_worktree(task_id, repo_path, workspace_dir, branch_name)
        else:
            workspace = self._create_directory_workspace(task_id, repo_path, workspace_dir)

        self.store.update_task(
            task_id,
            TaskUpdate(workspace_id=workspace.id, branch_name=workspace.branch_name),
        )

        await self.events.publish("workspace.created", workspace.model_dump())
        task_after = self.store.get_task(task_id)
        if task_after is not None:
            await self.events.publish("task.updated", task_after.model_dump())
        return workspace

    def _create_git_worktree(
        self, task_id: str, repo_path: Path, workspace_dir: Path, branch_name: str
    ) -> Workspace:
        self._prepare_workspace_dir(workspace_dir)
        branch_exists = self._git_branch_exists(repo_path, branch_name)
        base_ref = self._workspace_base_ref(repo_path)
        command = ["git", "-C", str(repo_path), "worktree", "add"]
        if not branch_exists:
            command.extend(["-b", branch_name])
        command.extend([str(workspace_dir)])
        if branch_exists:
            command.append(branch_name)
        else:
            command.append(base_ref)
        subprocess.run(command, check=True, capture_output=True, text=True)
        return self.store.upsert_workspace(
            task_id=task_id,
            repo_path=str(repo_path),
            workspace_path=str(workspace_dir),
            branch_name=branch_name,
            worktree_path=str(workspace_dir),
            kind=WorkspaceKind.GIT_WORKTREE,
            status=WorkspaceStatus.ACTIVE,
        )

    def _create_directory_workspace(
        self, task_id: str, repo_path: Path | None, workspace_dir: Path
    ) -> Workspace:
        self._prepare_workspace_dir(workspace_dir)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        return self.store.upsert_workspace(
            task_id=task_id,
            repo_path=str(repo_path) if repo_path else None,
            workspace_path=str(workspace_dir),
            branch_name=None,
            worktree_path=None,
            kind=WorkspaceKind.DIRECTORY,
            status=WorkspaceStatus.ACTIVE,
        )

    def _is_git_repo(self, repo_path: Path) -> bool:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    def _git_branch_exists(self, repo_path: Path, branch_name: str) -> bool:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--verify", branch_name],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def _workspace_branch_name(self, task_id: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", task_id).strip("-")
        return f"multybt/{safe}-{int(time.time())}"

    def _normalize_repo_path(self, repo_path: Path) -> Path:
        candidate = repo_path.resolve()
        if self._is_git_repo(candidate):
            result = subprocess.run(
                ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            )
            return Path(result.stdout.strip()).resolve()
        return candidate

    def _reject_managed_workspace_source(self, task_id: str, repo_path: Path) -> None:
        for workspace in self.store.list_workspaces():
            if workspace.task_id == task_id:
                continue
            managed_paths = [workspace.workspace_path, workspace.worktree_path]
            for managed_path in managed_paths:
                if not managed_path:
                    continue
                managed = Path(managed_path).expanduser().resolve()
                if repo_path == managed or managed in repo_path.parents:
                    raise ValueError(
                        "Task repo_path points to an existing Multy-Bt safe copy. "
                        "Link the original project folder instead."
                    )

    def _prepare_workspace_dir(self, workspace_dir: Path) -> None:
        resolved_workspace_dir = workspace_dir.resolve(strict=False)
        resolved_root = self.root.resolve()
        if resolved_root not in resolved_workspace_dir.parents:
            raise ValueError("Workspace path must stay inside the Multy-Bt workspace root")
        if workspace_dir.exists():
            if workspace_dir.is_symlink():
                raise ValueError("Workspace path cannot be a symlink")
            shutil.rmtree(workspace_dir)

    def _workspace_base_ref(self, repo_path: Path) -> str:
        branch_result = subprocess.run(
            ["git", "-C", str(repo_path), "symbolic-ref", "--quiet", "--short", "HEAD"],
            capture_output=True,
            text=True,
        )
        if branch_result.returncode == 0:
            return branch_result.stdout.strip()
        return "HEAD"

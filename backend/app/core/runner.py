from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from app.core.store import SUMMARY_RAW_MESSAGE_LIMIT, make_id, now_ms
from app.models import (
    AgentKind,
    AgentRegister,
    AgentStatus,
    AgentStatusUpdate,
    ClaudeLaunchRequest,
    CodexLaunchRequest,
    MessageType,
    Run,
    RunCreate,
    RunEventCreate,
    RunEventType,
    RunStatus,
    SenderType,
    TaskStatus,
    TargetType,
    TaskMessage,
    TaskUpdate,
)


class AgentRunManager:
    def __init__(self, store, events, workspace_manager=None) -> None:
        self.store = store
        self.events = events
        self.workspace_manager = workspace_manager
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._active_task_agents: set[tuple[str, str]] = set()
        # Default to repository root when task/repo/workspace cwd is missing.
        self._default_cwd = Path(__file__).resolve().parents[3]

    async def ensure_codex_agent(self) -> None:
        agent = self.store.register_agent(
            AgentRegister(
                id="codex_local",
                name="Codex Local",
                kind=AgentKind.CODEX,
                transport="cli",
                host=socket.gethostname(),
            )
        )
        await self.events.publish("agent.updated", agent.model_dump())

    async def ensure_claude_agent(self) -> None:
        agent = self.store.register_agent(
            AgentRegister(
                id="claude_local",
                name="Claude Code Local",
                kind=AgentKind.CLAUDE_CODE,
                transport="cli",
                host=socket.gethostname(),
            )
        )
        await self.events.publish("agent.updated", agent.model_dump())

    async def launch_codex(self, payload: CodexLaunchRequest) -> Run:
        task = self.store.get_task(payload.task_id)
        if task is None:
            raise ValueError("Task not found")

        await self.ensure_codex_agent()
        self._claim_agent_turn(task.id, "codex_local")
        try:
            existing_session = self.store.get_agent_session(task.id, "codex_local")
            prompt = self._compose_task_prompt(
                task,
                "codex_local",
                payload.prompt,
                resumed=existing_session is not None,
            )
            payload = payload.model_copy(
                update={
                    "prompt": prompt,
                    "session_id": existing_session.session_id if existing_session else None,
                }
            )
            cwd = await self._resolve_cwd(task.id, payload.cwd, task.repo_path)
            if existing_session is not None:
                self.store.upsert_agent_session(
                    task.id, "codex_local", existing_session.session_id, cwd
                )
            command_line = self._command_line_preview(payload, cwd)
            run = self.store.create_run(
                RunCreate(
                    task_id=payload.task_id,
                    agent_id="codex_local",
                    command_line=command_line,
                    cwd=cwd,
                )
            )
            await self.events.publish("run.created", run.model_dump())
            self.store.update_task(
                payload.task_id,
                TaskUpdate(status=TaskStatus.IN_PROGRESS, assigned_agent_id="codex_local"),
            )
            asyncio.create_task(self._execute_codex(run.id, payload, cwd))
            return run
        except Exception:
            self._release_agent_turn(task.id, "codex_local")
            raise

    async def launch_claude(self, payload: ClaudeLaunchRequest) -> Run:
        task = self.store.get_task(payload.task_id)
        if task is None:
            raise ValueError("Task not found")

        await self.ensure_claude_agent()
        self._claim_agent_turn(task.id, "claude_local")
        try:
            existing_session = self.store.get_agent_session(task.id, "claude_local")
            prompt = self._compose_task_prompt(
                task,
                "claude_local",
                payload.prompt,
                resumed=existing_session is not None,
            )
            payload = payload.model_copy(
                update={
                    "prompt": prompt,
                    "session_id": existing_session.session_id if existing_session else None,
                    "no_session_persistence": False,
                }
            )
            cwd = await self._resolve_cwd(task.id, payload.cwd, task.repo_path)
            if existing_session is not None:
                self.store.upsert_agent_session(
                    task.id, "claude_local", existing_session.session_id, cwd
                )
            command_line = self._command_line_preview_claude(payload)
            run = self.store.create_run(
                RunCreate(
                    task_id=payload.task_id,
                    agent_id="claude_local",
                    command_line=command_line,
                    cwd=cwd,
                )
            )
            await self.events.publish("run.created", run.model_dump())
            self.store.update_task(
                payload.task_id,
                TaskUpdate(status=TaskStatus.IN_PROGRESS, assigned_agent_id="claude_local"),
            )
            asyncio.create_task(self._execute_claude(run.id, payload, cwd))
            return run
        except Exception:
            self._release_agent_turn(task.id, "claude_local")
            raise

    async def stop_run(self, run_id: str) -> Run | None:
        run = self.store.get_run(run_id)
        process = self._processes.get(run_id)
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await process.wait()
        self._processes.pop(run_id, None)
        run = self.store.update_run_status(run_id, RunStatus.STOPPED)
        if run is not None:
            await self.events.publish("run.updated", run.model_dump())
            await self._emit_run_event(
                run_id,
                RunEventType.STATUS,
                {"status": RunStatus.STOPPED.value},
            )
        if run is not None:
            self._release_agent_turn(run.task_id, run.agent_id)
        return run

    async def _execute_codex(
        self, run_id: str, payload: CodexLaunchRequest, cwd: str
    ) -> None:
        await self.events.publish(
            "task.message_created",
            TaskMessage(
                id=make_id("msg"),
                task_id=payload.task_id,
                sender_type=SenderType.SYSTEM,
                sender_id="multy-bt",
                target_type=TargetType.BROADCAST,
                message_type=MessageType.PROGRESS,
                content="Codex run started.",
                created_at=now_ms(),
            ).model_dump(),
        )
        try:
            process = await self._spawn_process(
                self._build_codex_command(payload, cwd),
                cwd,
                stdin_text=payload.prompt,
            )
        except Exception as exc:
            await self._handle_launch_failure(run_id, "codex_local", payload.task_id, exc)
            return
        self._processes[run_id] = process
        run = self.store.update_run_pid(run_id, process.pid)
        if run is not None:
            await self.events.publish("run.updated", run.model_dump())
        await self._emit_run_event(
            run_id, RunEventType.STATUS, {"status": RunStatus.RUNNING.value, "pid": process.pid}
        )
        self.store.update_agent_status("codex_local", AgentStatusUpdate(status=AgentStatus.BUSY))

        stdout_task = asyncio.create_task(self._pump_stream(run_id, process.stdout, RunEventType.STDOUT))
        stderr_task = asyncio.create_task(self._pump_stream(run_id, process.stderr, RunEventType.STDERR))
        return_code = await process.wait()
        await asyncio.gather(stdout_task, stderr_task)
        self._processes.pop(run_id, None)
        self._release_agent_turn(payload.task_id, "codex_local")
        self.store.update_agent_status("codex_local", AgentStatusUpdate(status=AgentStatus.IDLE))

        if return_code == 0:
            completed = self.store.update_run_status(run_id, RunStatus.COMPLETED, exit_code=0)
            if completed is not None:
                await self.events.publish("run.updated", completed.model_dump())
            await self._emit_run_event(
                run_id,
                RunEventType.RESULT,
                {"status": RunStatus.COMPLETED.value, "exit_code": 0},
            )
        else:
            failed = self.store.update_run_status(run_id, RunStatus.FAILED, exit_code=return_code)
            if failed is not None:
                await self.events.publish("run.updated", failed.model_dump())
            await self._emit_run_event(
                run_id,
                RunEventType.RESULT,
                {"status": RunStatus.FAILED.value, "exit_code": return_code},
            )

    async def _execute_claude(
        self, run_id: str, payload: ClaudeLaunchRequest, cwd: str
    ) -> None:
        await self.events.publish(
            "task.message_created",
            TaskMessage(
                id=make_id("msg"),
                task_id=payload.task_id,
                sender_type=SenderType.SYSTEM,
                sender_id="multy-bt",
                target_type=TargetType.BROADCAST,
                message_type=MessageType.PROGRESS,
                content="Claude run started.",
                created_at=now_ms(),
            ).model_dump(),
        )
        try:
            process = await self._spawn_process(self._build_claude_command(payload), cwd)
        except Exception as exc:
            await self._handle_launch_failure(run_id, "claude_local", payload.task_id, exc)
            return
        self._processes[run_id] = process
        run = self.store.update_run_pid(run_id, process.pid)
        if run is not None:
            await self.events.publish("run.updated", run.model_dump())
        await self._emit_run_event(
            run_id, RunEventType.STATUS, {"status": RunStatus.RUNNING.value, "pid": process.pid}
        )
        self.store.update_agent_status("claude_local", AgentStatusUpdate(status=AgentStatus.BUSY))

        stdout_task = asyncio.create_task(
            self._pump_stream(run_id, process.stdout, RunEventType.STDOUT)
        )
        stderr_task = asyncio.create_task(
            self._pump_stream(run_id, process.stderr, RunEventType.STDERR)
        )
        return_code = await process.wait()
        await asyncio.gather(stdout_task, stderr_task)
        self._processes.pop(run_id, None)
        self._release_agent_turn(payload.task_id, "claude_local")
        self.store.update_agent_status("claude_local", AgentStatusUpdate(status=AgentStatus.IDLE))

        if return_code == 0:
            completed = self.store.update_run_status(run_id, RunStatus.COMPLETED, exit_code=0)
            if completed is not None:
                await self.events.publish("run.updated", completed.model_dump())
            await self._emit_run_event(
                run_id,
                RunEventType.RESULT,
                {"status": RunStatus.COMPLETED.value, "exit_code": 0},
            )
        else:
            failed = self.store.update_run_status(run_id, RunStatus.FAILED, exit_code=return_code)
            if failed is not None:
                await self.events.publish("run.updated", failed.model_dump())
            await self._emit_run_event(
                run_id,
                RunEventType.RESULT,
                {"status": RunStatus.FAILED.value, "exit_code": return_code},
            )

    async def _spawn_process(
        self, command: Sequence[str], cwd: str, stdin_text: str | None = None
    ) -> asyncio.subprocess.Process:
        env = os.environ.copy()
        # Remove parent Claude marker so nested runs can start cleanly.
        env.pop("CLAUDECODE", None)
        stdin_pipe = asyncio.subprocess.PIPE if stdin_text is not None else None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=stdin_pipe,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
        except OSError as exc:
            # On Windows, CLI tools often install as .cmd/.ps1 shims.
            if sys.platform != "win32" or getattr(exc, "winerror", None) not in {2, 193}:
                raise
            cmd_str = subprocess.list2cmdline([str(part) for part in command])
            process = await asyncio.create_subprocess_shell(
                cmd_str,
                stdin=stdin_pipe,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
        if stdin_text is not None and process.stdin is not None:
            try:
                process.stdin.write(stdin_text.encode("utf-8"))
                process.stdin.write(b"\n")
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
            process.stdin.close()
        return process

    async def _handle_launch_failure(
        self, run_id: str, agent_id: str, task_id: str, exc: Exception
    ) -> None:
        error_text = f"Failed to launch agent process: {exc}"
        self._release_agent_turn(task_id, agent_id)
        self.store.update_agent_status(agent_id, AgentStatusUpdate(status=AgentStatus.IDLE))
        failed = self.store.update_run_status(run_id, RunStatus.FAILED, exit_code=1)
        if failed is not None:
            await self.events.publish("run.updated", failed.model_dump())
        await self._emit_run_event(run_id, RunEventType.STDERR, {"text": error_text})
        await self._emit_run_event(
            run_id,
            RunEventType.RESULT,
            {"status": RunStatus.FAILED.value, "exit_code": 1, "error": str(exc)},
        )
        task_message = TaskMessage(
            id=make_id("msg"),
            task_id=task_id,
            sender_type=SenderType.SYSTEM,
            sender_id="multy-bt",
            target_type=TargetType.BROADCAST,
            message_type=MessageType.ERROR,
            content=error_text,
            created_at=now_ms(),
        )
        self.store.add_message(task_id, task_message)
        await self.events.publish("task.message_created", task_message.model_dump())

    async def _pump_stream(
        self,
        run_id: str,
        stream: asyncio.StreamReader | None,
        event_type: RunEventType,
    ) -> None:
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip("\n")
            payload: dict[str, object] = {"text": text}
            try:
                payload["json"] = json.loads(text)
            except json.JSONDecodeError:
                pass
            await self._emit_run_event(run_id, event_type, payload)

    async def _emit_run_event(
        self, run_id: str, event_type: RunEventType, payload: dict[str, object]
    ) -> None:
        event = self.store.add_run_event(
            run_id, RunEventCreate(event_type=event_type, payload=payload)
        )
        if event is not None:
            await self.events.publish("run.event", event.model_dump())
            await self._maybe_capture_agent_session(event)
            await self._maybe_publish_agent_message(event)

    async def _maybe_capture_agent_session(self, event) -> None:
        if event.event_type != RunEventType.STDOUT:
            return
        run = self.store.get_run(event.run_id)
        if run is None:
            return
        json_payload = event.payload.get("json")
        if not isinstance(json_payload, dict):
            return
        if run.agent_id == "codex_local":
            if json_payload.get("type") != "thread.started":
                return
            thread_id = json_payload.get("thread_id")
            if not isinstance(thread_id, str) or not thread_id.strip():
                return
            self.store.upsert_agent_session(run.task_id, run.agent_id, thread_id.strip(), run.cwd)
            return
        if run.agent_id == "claude_local":
            if json_payload.get("type") != "system" or json_payload.get("subtype") != "init":
                return
            session_id = json_payload.get("session_id")
            if not isinstance(session_id, str) or not session_id.strip():
                return
            self.store.upsert_agent_session(run.task_id, run.agent_id, session_id.strip(), run.cwd)

    async def _maybe_publish_agent_message(self, event) -> None:
        if event.event_type != RunEventType.STDOUT:
            return
        run = self.store.get_run(event.run_id)
        if run is None:
            return
        payload = event.payload
        json_payload = payload.get("json")
        if not isinstance(json_payload, dict):
            return

        message_text: str | None = None
        if json_payload.get("type") == "assistant":
            message = json_payload.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, list):
                    text_parts: list[str] = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text = item.get("text")
                            if isinstance(text, str) and text.strip():
                                text_parts.append(text.strip())
                    if text_parts:
                        message_text = "\n".join(text_parts)
        elif json_payload.get("type") == "item.completed":
            item = json_payload.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    message_text = text.strip()
        elif json_payload.get("type") == "result":
            if run.agent_id == "claude_local":
                return
            result = json_payload.get("result")
            if isinstance(result, str) and result.strip():
                message_text = result.strip()

        if not message_text:
            return

        task_message = TaskMessage(
            id=make_id("msg"),
            task_id=run.task_id,
            sender_type=SenderType.AGENT,
            sender_id=run.agent_id,
            target_type=TargetType.BROADCAST,
            message_type=MessageType.PROGRESS,
            content=message_text,
            created_at=now_ms(),
        )
        self.store.add_message(run.task_id, task_message)
        await self.events.publish("task.message_created", task_message.model_dump())

    def _claim_agent_turn(self, task_id: str, agent_id: str) -> None:
        key = (task_id, agent_id)
        if key in self._active_task_agents:
            raise ValueError(f"{agent_id} already has an active turn for this task")
        self._active_task_agents.add(key)

    def _release_agent_turn(self, task_id: str, agent_id: str) -> None:
        self._active_task_agents.discard((task_id, agent_id))

    def _compose_task_prompt(
        self, task, agent_id: str, prompt: str, *, resumed: bool = False
    ) -> str:
        if resumed:
            return "\n".join(
                [
                    "You are resuming the same Multy-Bt conversation session.",
                    "Only respond to the explicit request in this new turn.",
                    "Do not continue prior work on your own.",
                    "Do not run extra checks, scans, edits, or follow-up tasks unless the new turn explicitly asks for them.",
                    "If the new turn is ambiguous, ask a clarifying question instead of choosing additional work yourself.",
                    f"Task title: {task.title}",
                    f"Repo path: {task.repo_path or 'No repo path provided.'}",
                    "",
                    "New turn:",
                    prompt,
                ]
            )

        messages = self.store.list_messages(task.id)
        stored_summary = self.store.get_task_context_summary(task.id)
        if stored_summary is None and len(messages) > SUMMARY_RAW_MESSAGE_LIMIT:
            stored_summary = self.store.rebuild_task_context_summary(task.id)
        relevant_messages = [
            message
            for message in messages
            if message.target_type in {None, TargetType.BROADCAST}
            or message.target_id == agent_id
            or message.sender_id == agent_id
        ]
        recent_messages = relevant_messages[-SUMMARY_RAW_MESSAGE_LIMIT:]

        context_lines = [
            "You are working inside an existing Multy-Bt task.",
            "Only handle the explicit current turn.",
            "Do not proactively continue adjacent work unless the user explicitly asks.",
            "If the current turn is ambiguous, ask a clarifying question before acting.",
            "",
            "Task context:",
            f"- Title: {task.title}",
            f"- Summary: {task.summary or 'No summary provided.'}",
            f"- Repo path: {task.repo_path or 'No repo path provided.'}",
            f"- Branch: {task.branch_name or 'No branch assigned.'}",
            "",
            "Recent task conversation:",
        ]

        if stored_summary and stored_summary.summary_text:
            context_lines.append(stored_summary.summary_text)
            context_lines.append("")

        if recent_messages:
            context_lines.append("Most recent raw turns:")
            for message in recent_messages:
                target = "everyone"
                if message.target_type == TargetType.AGENT:
                    target = message.target_id or "agent"
                context_lines.append(
                    f"- {message.sender_type.value}:{message.sender_id} -> {target} [{message.message_type.value}] {message.content}"
                )
        else:
            if stored_summary and stored_summary.summary_text:
                context_lines.append("- No recent raw turns for this helper.")
            else:
                context_lines.append("- No prior messages.")

        context_lines.extend(
            [
                "",
                "Current turn:",
                prompt,
            ]
        )
        return "\n".join(context_lines)

    async def _resolve_cwd(
        self, task_id: str, explicit_cwd: str | None, repo_path: str | None
    ) -> str:
        if explicit_cwd:
            return str(Path(explicit_cwd).resolve())

        workspace = self.store.get_workspace_by_task(task_id)
        if workspace is not None and Path(workspace.workspace_path).exists():
            return workspace.workspace_path

        if repo_path and self.workspace_manager is not None:
            workspace = await self.workspace_manager.create_for_task(task_id)
            return workspace.workspace_path

        if repo_path:
            return str(Path(repo_path).resolve())
        return str(self._default_cwd)

    def _build_codex_command(
        self, payload: CodexLaunchRequest, cwd: str
    ) -> Sequence[str]:
        if payload.session_id:
            command = ["codex", "exec", "resume", "--json"]
            if payload.skip_git_repo_check:
                command.append("--skip-git-repo-check")
            if payload.full_auto:
                command.append("--full-auto")
            if payload.model:
                command.extend(["--model", payload.model])
            command.append(payload.session_id)
            command.append("-")
            return command

        command = ["codex", "exec", "--json", "-C", cwd]
        if payload.skip_git_repo_check:
            command.append("--skip-git-repo-check")
        if payload.full_auto:
            command.append("--full-auto")
        if payload.sandbox:
            command.extend(["--sandbox", payload.sandbox.value])
        if payload.model:
            command.extend(["--model", payload.model])
        if payload.profile:
            command.extend(["--profile", payload.profile])
        command.append("-")
        return command

    def _command_line_preview(self, payload: CodexLaunchRequest, cwd: str) -> str:
        if payload.session_id:
            preview = ["codex exec resume --json"]
            if payload.skip_git_repo_check:
                preview.append("--skip-git-repo-check")
            if payload.full_auto:
                preview.append("--full-auto")
            if payload.model:
                preview.append(f"--model {payload.model}")
            preview.append(payload.session_id)
            preview.append("<prompt>")
            return " ".join(preview)

        preview = ["codex exec --json", f"-C {cwd}"]
        if payload.skip_git_repo_check:
            preview.append("--skip-git-repo-check")
        if payload.full_auto:
            preview.append("--full-auto")
        preview.append(f"--sandbox {payload.sandbox.value}")
        if payload.model:
            preview.append(f"--model {payload.model}")
        if payload.profile:
            preview.append(f"--profile {payload.profile}")
        preview.append("<prompt>")
        return " ".join(preview)

    def _build_claude_command(self, payload: ClaudeLaunchRequest) -> Sequence[str]:
        command = ["claude"]
        if payload.print_mode:
            command.append("--print")
        if payload.no_session_persistence:
            command.append("--no-session-persistence")
        if payload.session_id:
            command.extend(["--resume", payload.session_id])
        command.extend(["--output-format", payload.output_format])
        if payload.output_format == "stream-json":
            command.append("--verbose")
        command.extend(["--permission-mode", payload.permission_mode.value])
        if payload.model:
            command.extend(["--model", payload.model])
        command.append(payload.prompt)
        return command

    def _command_line_preview_claude(self, payload: ClaudeLaunchRequest) -> str:
        preview = ["claude"]
        if payload.print_mode:
            preview.append("--print")
        if payload.no_session_persistence:
            preview.append("--no-session-persistence")
        if payload.session_id:
            preview.append(f"--resume {payload.session_id}")
        preview.append(f"--output-format {payload.output_format}")
        if payload.output_format == "stream-json":
            preview.append("--verbose")
        preview.append(f"--permission-mode {payload.permission_mode.value}")
        if payload.model:
            preview.append(f"--model {payload.model}")
        preview.append("<prompt>")
        return " ".join(preview)

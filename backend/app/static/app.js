const state = {
  tasks: [],
  agents: [],
  runs: [],
  workspaces: [],
  messagesByTask: new Map(),
  runEventsByRun: new Map(),
  summariesByTask: new Map(),
  events: [],
  selectedTaskId: null,
  selectedRunId: null,
};

let refreshTimer = null;
let socketRetryTimer = null;

const els = {
  taskForm: document.getElementById('taskForm'),
  taskList: document.getElementById('taskList'),
  taskCount: document.getElementById('taskCount'),
  deleteTaskBtn: document.getElementById('deleteTaskBtn'),
  activeTaskTitle: document.getElementById('activeTaskTitle'),
  activeTaskMeta: document.getElementById('activeTaskMeta'),
  taskSummaryView: document.getElementById('taskSummaryView'),
  taskContextSummaryView: document.getElementById('taskContextSummaryView'),
  taskContextUpdatedView: document.getElementById('taskContextUpdatedView'),
  taskContextCountView: document.getElementById('taskContextCountView'),
  taskStatusBadge: document.getElementById('taskStatusBadge'),
  taskRepoPathView: document.getElementById('taskRepoPathView'),
  taskAssignedView: document.getElementById('taskAssignedView'),
  taskBranchView: document.getElementById('taskBranchView'),
  taskPriorityView: document.getElementById('taskPriorityView'),
  workspaceKindBadge: document.getElementById('workspaceKindBadge'),
  workspacePathView: document.getElementById('workspacePathView'),
  workspaceRepoView: document.getElementById('workspaceRepoView'),
  workspaceWorktreeView: document.getElementById('workspaceWorktreeView'),
  workspaceHint: document.getElementById('workspaceHint'),
  messageList: document.getElementById('messageList'),
  messageCount: document.getElementById('messageCount'),
  messageInput: document.getElementById('messageInput'),
  messageType: document.getElementById('messageType'),
  messageTarget: document.getElementById('messageTarget'),
  sendMessageBtn: document.getElementById('sendMessageBtn'),
  sendAndAskBtn: document.getElementById('sendAndAskBtn'),
  runList: document.getElementById('runList'),
  runCount: document.getElementById('runCount'),
  runDetailBadge: document.getElementById('runDetailBadge'),
  runDetailMeta: document.getElementById('runDetailMeta'),
  runEventList: document.getElementById('runEventList'),
  runEventFilter: document.getElementById('runEventFilter'),
  stopRunBtn: document.getElementById('stopRunBtn'),
  agentList: document.getElementById('agentList'),
  agentCount: document.getElementById('agentCount'),
  eventFeed: document.getElementById('eventFeed'),
  socketBadge: document.getElementById('socketBadge'),
  createWorkspaceBtn: document.getElementById('createWorkspaceBtn'),
  launchCodexBtn: document.getElementById('launchCodexBtn'),
  launchClaudeBtn: document.getElementById('launchClaudeBtn'),
  launchPrompt: document.getElementById('launchPrompt'),
  agentPicker: document.getElementById('agentPicker'),
  sendTaskBtn: document.getElementById('sendTaskBtn'),
  composerHint: document.getElementById('composerHint'),
  refreshAllBtn: document.getElementById('refreshAllBtn'),
  workflowHelpBtn: document.getElementById('workflowHelpBtn'),
  workflowDialog: document.getElementById('workflowDialog'),
  closeWorkflowHelpBtn: document.getElementById('closeWorkflowHelpBtn'),
  refreshSummaryBtn: document.getElementById('refreshSummaryBtn'),
  taskStatusFlow: document.getElementById('taskStatusFlow'),
  template: document.getElementById('taskItemTemplate'),
  handoffTemplate: document.getElementById('handoffTemplate'),
};

const FRIENDLY_STATUS = {
  todo: 'Ready',
  in_progress: 'In progress',
  blocked: 'Blocked',
  review: 'Needs review',
  done: 'Done',
  cancelled: 'Stopped',
  queued: 'Queued',
  running: 'Working',
  waiting_approval: 'Waiting for you',
  completed: 'Finished',
  failed: 'Needs attention',
  stopped: 'Stopped',
  idle: 'Available',
  busy: 'Busy',
  offline: 'Offline',
  error: 'Problem',
};

const FRIENDLY_PRIORITY = {
  high: 'Urgent',
  normal: 'Normal pace',
  low: 'Can wait',
};

const FRIENDLY_MESSAGE_TYPE = {
  instruction: 'Instruction',
  question: 'Question',
  proposal: 'Proposal',
  decision: 'Decision',
  progress: 'Progress',
  artifact: 'Artifact',
  handoff: 'Transfer',
  error: 'Error',
};

const FRIENDLY_RUN_EVENT = {
  stdout: 'Output',
  stderr: 'Error output',
  status: 'Status',
  approval_requested: 'Approval requested',
  approval_resolved: 'Approval resolved',
  result: 'Result',
  heartbeat: 'Heartbeat',
};

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function formatTime(timestamp) {
  if (!timestamp) return '-';
  return new Date(timestamp).toLocaleString();
}

function labelForStatus(status) {
  return FRIENDLY_STATUS[status] || String(status || 'unknown').replaceAll('_', ' ');
}

function labelForPriority(priority) {
  return FRIENDLY_PRIORITY[priority] || priority || '-';
}

function labelForMessageType(type) {
  return FRIENDLY_MESSAGE_TYPE[type] || String(type || 'message').replaceAll('_', ' ');
}

function labelForRunEvent(type) {
  return FRIENDLY_RUN_EVENT[type] || String(type || 'event').replaceAll('_', ' ');
}

function labelForMessageTarget(message) {
  if (!message?.target_type || message.target_type === 'broadcast') {
    return 'To everyone';
  }
  return `To ${message.target_id || 'agent'}`;
}

function labelForAgentId(agentId) {
  if (agentId === 'codex_local') return 'Codex';
  if (agentId === 'claude_local') return 'Claude';
  return agentId || 'agent';
}

function statusDot(status) {
  const safe = String(status || 'unknown').replaceAll(' ', '_');
  return `<span class="status-dot ${safe}"></span>${escapeHtml(labelForStatus(status))}`;
}

function summarize(text, max = 96) {
  const value = (text || '').trim();
  if (!value) return 'No extra context yet.';
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

function summarizeForTransfer(text, max = 320) {
  const normalized = String(text || '').trim();
  if (!normalized) return '';

  const paragraphs = normalized
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter(Boolean);
  const firstParagraph = paragraphs[0] || normalized;

  const bulletLines = firstParagraph
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.startsWith('-') || /^\d+\./.test(line));

  const candidate = bulletLines.length ? bulletLines.slice(0, 3).join('\n') : firstParagraph;
  return summarize(candidate, max);
}

function eventPreview(event) {
  if (event?.payload?.text) return event.payload.text;
  return JSON.stringify(event?.payload ?? {}, null, 2);
}

function isTerminalRunStatus(status) {
  return ['completed', 'failed', 'stopped'].includes(status);
}

async function api(path, options = {}) {
  const response = await fetch(`/api/v1${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function getSelectedTask() {
  return state.tasks.find((task) => task.id === state.selectedTaskId) || null;
}

function getSelectedWorkspace() {
  const task = getSelectedTask();
  if (!task) return null;
  return state.workspaces.find((workspace) => workspace.task_id === task.id) || null;
}

function getSelectedTaskSummary() {
  const task = getSelectedTask();
  if (!task) return null;
  return state.summariesByTask.get(task.id) || null;
}

function getTaskRuns(taskId = state.selectedTaskId) {
  if (!taskId) return [];
  return state.runs.filter((run) => run.task_id === taskId);
}

function getSelectedRun() {
  return state.runs.find((run) => run.id === state.selectedRunId) || null;
}

function ensureSelectedRun() {
  const runs = getTaskRuns();
  if (!runs.length) {
    state.selectedRunId = null;
    return;
  }
  if (!runs.find((run) => run.id === state.selectedRunId)) {
    state.selectedRunId = runs[0].id;
  }
}

function updateActionState() {
  const task = getSelectedTask();
  const run = getSelectedRun();
  const enabled = Boolean(task);
  const canAskFromMessage = enabled && els.messageTarget.value !== 'broadcast';
  els.createWorkspaceBtn.disabled = !enabled;
  els.launchCodexBtn.disabled = !enabled;
  els.launchClaudeBtn.disabled = !enabled;
  els.sendTaskBtn.disabled = !enabled;
  els.sendMessageBtn.disabled = !enabled;
  els.sendAndAskBtn.disabled = !canAskFromMessage;
  els.stopRunBtn.disabled = !run || isTerminalRunStatus(run.status);
  els.refreshSummaryBtn.disabled = !enabled;
  els.deleteTaskBtn.disabled = !enabled;
  for (const button of els.taskStatusFlow.querySelectorAll('[data-status]')) {
    button.disabled = !enabled;
  }

  if (!task) {
    els.composerHint.textContent = 'Choose a task first, then decide who should handle it.';
    return;
  }

  const workspace = getSelectedWorkspace();
  if (task.repo_path && !workspace) {
    els.composerHint.textContent = 'This task points to a project folder. We will prepare a safe copy before handing it to an agent.';
  } else {
    els.composerHint.textContent = 'Write the next instruction in normal language. The selected helper will receive it in this task context.';
  }
}

function renderMessageTargetOptions() {
  const current = els.messageTarget.value;
  const dynamicOptions = state.agents
    .map((agent) => `<option value="${escapeHtml(agent.id)}">${escapeHtml(agent.name)}</option>`)
    .join('');
  els.messageTarget.innerHTML = `
    <option value="broadcast">Everyone following this task</option>
    ${dynamicOptions}
  `;
  if ([...els.messageTarget.options].some((option) => option.value === current)) {
    els.messageTarget.value = current;
  }
}

function renderTasks() {
  els.taskCount.textContent = String(state.tasks.length);
  if (!state.tasks.length) {
    els.taskList.innerHTML = '<div class="empty-state">No tasks yet. Start with a short description of what needs to happen.</div>';
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const task of state.tasks) {
    const node = els.template.content.firstElementChild.cloneNode(true);
    node.classList.toggle('active', task.id === state.selectedTaskId);
    node.querySelector('.task-title').textContent = task.title;
    node.querySelector('.task-priority').textContent = labelForPriority(task.priority);
    node.querySelector('.task-status').innerHTML = statusDot(task.status);
    node.querySelector('.task-agent').textContent = task.assigned_agent_id ? `With ${task.assigned_agent_id}` : 'Waiting for assignment';
    node.querySelector('.task-summary-preview').textContent = summarize(task.summary);
    node.addEventListener('click', () => selectTask(task.id));
    fragment.appendChild(node);
  }
  els.taskList.replaceChildren(fragment);
}

function renderTaskDetail() {
  const task = getSelectedTask();
  const workspace = getSelectedWorkspace();
  const taskSummary = getSelectedTaskSummary();
  for (const button of els.taskStatusFlow.querySelectorAll('[data-status]')) {
    button.classList.remove('active');
  }
  if (!task) {
    els.activeTaskTitle.textContent = 'Select a task';
    els.activeTaskMeta.textContent = 'Choose a task to see context, conversation, and recent activity.';
    els.taskSummaryView.textContent = 'No task selected.';
    els.taskContextSummaryView.textContent = 'No saved summary yet.';
    els.taskContextSummaryView.className = 'detail-copy muted';
    els.taskContextUpdatedView.textContent = 'No saved memory';
    els.taskContextUpdatedView.className = 'tag muted';
    els.taskContextCountView.textContent = '0 source messages';
    els.taskContextCountView.className = 'tag muted';
    els.taskStatusBadge.textContent = 'No task';
    els.taskStatusBadge.className = 'tag muted';
    els.taskRepoPathView.textContent = '-';
    els.taskAssignedView.textContent = '-';
    els.taskBranchView.textContent = '-';
    els.taskPriorityView.textContent = '-';
    els.workspaceKindBadge.textContent = 'Not prepared';
    els.workspaceKindBadge.className = 'tag muted';
    els.workspacePathView.textContent = '-';
    els.workspaceRepoView.textContent = '-';
    els.workspaceWorktreeView.textContent = '-';
    els.workspaceHint.textContent = 'If this task points to a code project, prepare a safe copy before asking an agent to work.';
    return;
  }

  els.activeTaskTitle.textContent = task.title;
  els.activeTaskMeta.textContent = `Created by ${task.created_by} at ${formatTime(task.created_at)}`;
  els.taskSummaryView.textContent = task.summary || 'No extra context yet.';
  els.taskStatusBadge.textContent = labelForStatus(task.status);
  els.taskStatusBadge.className = 'tag';
  for (const button of els.taskStatusFlow.querySelectorAll('[data-status]')) {
    button.classList.toggle('active', button.dataset.status === task.status);
  }
  els.taskRepoPathView.textContent = task.repo_path || 'No project folder linked';
  els.taskAssignedView.textContent = task.assigned_agent_id || 'Not assigned yet';
  els.taskBranchView.textContent = task.branch_name || '-';
  els.taskPriorityView.textContent = labelForPriority(task.priority);
  if (taskSummary?.summary_text) {
    els.taskContextSummaryView.textContent = taskSummary.summary_text;
    els.taskContextSummaryView.className = 'detail-copy';
    els.taskContextUpdatedView.textContent = `Saved ${formatTime(taskSummary.updated_at)}`;
    els.taskContextUpdatedView.className = 'tag';
    els.taskContextCountView.textContent = `${taskSummary.source_message_count} source messages`;
    els.taskContextCountView.className = 'tag';
  } else {
    els.taskContextSummaryView.textContent = 'No saved summary yet. Once the conversation grows, Multy-Bt will keep a reusable memory here.';
    els.taskContextSummaryView.className = 'detail-copy muted';
    els.taskContextUpdatedView.textContent = 'No saved memory';
    els.taskContextUpdatedView.className = 'tag muted';
    els.taskContextCountView.textContent = '0 source messages';
    els.taskContextCountView.className = 'tag muted';
  }

  if (workspace) {
    els.workspaceKindBadge.textContent = workspace.kind === 'git_worktree' ? 'Prepared' : 'Folder ready';
    els.workspaceKindBadge.className = 'tag';
    els.workspacePathView.textContent = workspace.workspace_path;
    els.workspaceRepoView.textContent = workspace.repo_path || '-';
    els.workspaceWorktreeView.textContent = workspace.worktree_path || '-';
    els.workspaceHint.textContent = 'This task already has a safe working area. Agents can work there without touching the original project directly.';
  } else {
    els.workspaceKindBadge.textContent = task.repo_path ? 'Needs setup' : 'Optional';
    els.workspaceKindBadge.className = task.repo_path ? 'tag' : 'tag muted';
    els.workspacePathView.textContent = '-';
    els.workspaceRepoView.textContent = task.repo_path || 'No project folder linked';
    els.workspaceWorktreeView.textContent = '-';
    els.workspaceHint.textContent = task.repo_path
      ? 'This task has a linked project. Prepare a safe copy before asking an agent to modify files.'
      : 'No project folder is linked, so a safe copy is optional for this task.';
  }
}

function renderMessages() {
  const task = getSelectedTask();
  const messages = task ? (state.messagesByTask.get(task.id) || []) : [];
  els.messageCount.textContent = String(messages.length);
  if (!messages.length) {
    els.messageList.innerHTML = '<div class="empty-state">Messages and handoffs for this task will appear here.</div>';
    return;
  }
  const sortedMessages = [...messages]
    .sort((a, b) => b.created_at - a.created_at)
  els.messageList.innerHTML = sortedMessages
    .map((message) => `
      <article class="timeline-item">
        <div class="headline">
          <strong>${escapeHtml(labelForMessageType(message.message_type))}</strong>
          <span class="muted small">${formatTime(message.created_at)}</span>
        </div>
        <p class="muted small">${escapeHtml(message.sender_type)} · ${escapeHtml(message.sender_id)} · ${escapeHtml(labelForMessageTarget(message))}</p>
        <p>${escapeHtml(message.content)}</p>
        ${message.sender_type === 'agent' ? `<div class="handoff-slot" data-message-id="${escapeHtml(message.id)}"></div>` : ''}
      </article>
    `)
    .join('');

  for (const slot of els.messageList.querySelectorAll('.handoff-slot')) {
    const message = sortedMessages.find((item) => item.id === slot.dataset.messageId);
    if (!message) continue;
    const handoff = els.handoffTemplate.content.firstElementChild.cloneNode(true);
    const select = handoff.querySelector('.handoff-target');
    const mode = handoff.querySelector('.handoff-mode');
    const note = handoff.querySelector('.handoff-note');
    const button = handoff.querySelector('.handoff-btn');
    if (message.sender_id === 'codex_local') {
      select.value = 'claude_local';
    }
    if (message.sender_id === 'claude_local') {
      select.value = 'codex_local';
    }
    button.textContent = `Transfer to ${labelForAgentId(select.value)}`;
    select.addEventListener('change', () => {
      button.textContent = `Transfer to ${labelForAgentId(select.value)}`;
    });
    button.addEventListener('click', async () => {
      try {
        await handoffMessage(message, select.value, note.value.trim(), mode.value);
      } catch (error) {
        alert(`Transfer failed: ${error.message}`);
      }
    });
    slot.replaceWith(handoff);
  }
}

function renderRuns() {
  const runs = getTaskRuns();
  els.runCount.textContent = String(runs.length);
  if (!runs.length) {
    els.runList.innerHTML = '<div class="empty-state">When a helper starts working, their activity will appear here.</div>';
    return;
  }
  els.runList.innerHTML = runs
    .map((run) => `
      <button class="timeline-item ${run.id === state.selectedRunId ? 'active' : ''}" type="button" data-run-id="${escapeHtml(run.id)}">
        <div class="headline">
          <strong>${escapeHtml(run.agent_id)}</strong>
          <span>${statusDot(run.status)}</span>
        </div>
        <p class="codeish">${escapeHtml(run.cwd)}</p>
        <p class="muted small">Started ${formatTime(run.started_at)}</p>
      </button>
    `)
    .join('');

  for (const button of els.runList.querySelectorAll('[data-run-id]')) {
    button.addEventListener('click', async () => {
      await selectRun(button.dataset.runId);
    });
  }
}

function renderRunDetail() {
  const run = getSelectedRun();
  if (!run) {
    els.runDetailBadge.textContent = 'No activity';
    els.runDetailBadge.className = 'tag muted';
    els.runDetailMeta.textContent = 'Choose an activity item to inspect its output.';
    els.runEventList.innerHTML = '<div class="empty-state">Execution output will appear here after you select an activity.</div>';
    els.stopRunBtn.disabled = true;
    return;
  }

  const runEvents = state.runEventsByRun.get(run.id) || [];
  const filter = els.runEventFilter.value;
  const visibleEvents = filter === 'errors'
    ? runEvents.filter((event) => event.event_type === 'stderr')
    : runEvents;
  els.runDetailBadge.textContent = labelForStatus(run.status);
  els.runDetailBadge.className = 'tag';
  els.runDetailMeta.textContent = `${run.agent_id} in ${run.cwd}`;
  els.stopRunBtn.disabled = isTerminalRunStatus(run.status);

  if (!runEvents.length) {
    els.runEventList.innerHTML = '<div class="empty-state">No detailed output yet for this activity.</div>';
    return;
  }

  if (!visibleEvents.length) {
    els.runEventList.innerHTML = '<div class="empty-state">No error output for this activity.</div>';
    return;
  }

  els.runEventList.innerHTML = visibleEvents
    .map((event) => `
      <article class="event-item">
        <div class="headline">
          <strong>${escapeHtml(labelForRunEvent(event.event_type))}</strong>
          <span class="muted small">${formatTime(event.created_at)}</span>
        </div>
        <pre class="codeish">${escapeHtml(eventPreview(event))}</pre>
      </article>
    `)
    .join('');
}

function renderAgents() {
  els.agentCount.textContent = String(state.agents.length);
  if (!state.agents.length) {
    els.agentList.innerHTML = '<div class="empty-state">Helpers will show up here after they register or start work.</div>';
    return;
  }
  els.agentList.innerHTML = state.agents
    .map((agent) => `
      <article class="agent-item">
        <div class="headline">
          <strong>${escapeHtml(agent.name)}</strong>
          <span>${statusDot(agent.status)}</span>
        </div>
        <p class="muted small">${escapeHtml(agent.kind)} · ${escapeHtml(agent.transport)}</p>
        <p class="codeish">${escapeHtml(agent.host)}</p>
      </article>
    `)
    .join('');
}

function renderEvents() {
  if (!state.events.length) {
    els.eventFeed.innerHTML = '<div class="empty-state">Recent task updates will stream here as they happen.</div>';
    return;
  }
  els.eventFeed.innerHTML = state.events
    .map((event) => `
      <article class="event-item">
        <div class="headline">
          <strong>${escapeHtml(event.event)}</strong>
          <span class="muted small">${formatTime(event.timestamp)}</span>
        </div>
        <pre class="codeish">${escapeHtml(JSON.stringify(event.payload, null, 2))}</pre>
      </article>
    `)
    .join('');
}

function renderAll() {
  renderMessageTargetOptions();
  updateActionState();
  renderTasks();
  renderTaskDetail();
  renderMessages();
  renderRuns();
  renderRunDetail();
  renderAgents();
  renderEvents();
}

async function loadMessages(taskId) {
  if (!taskId) return;
  const messages = await api(`/tasks/${taskId}/messages`);
  const deduped = [];
  for (const message of messages) {
    if (!deduped.find((item) => item.id === message.id)) {
      deduped.push(message);
    }
  }
  state.messagesByTask.set(taskId, deduped);
}

async function loadTaskSummary(taskId, rebuildIfMissing = false) {
  if (!taskId) return;
  let summary = await api(`/tasks/${taskId}/summary`);
  const messageCount = (state.messagesByTask.get(taskId) || []).length;
  if (!summary && rebuildIfMissing && messageCount > 6) {
    summary = await api(`/tasks/${taskId}/summary/rebuild`, { method: 'POST' });
  }
  state.summariesByTask.set(taskId, summary);
}

async function loadRunEvents(runId) {
  if (!runId) return;
  const events = await api(`/runs/${runId}/events`);
  state.runEventsByRun.set(runId, events);
}

async function refreshData() {
  const [tasks, agents, runs, workspaces] = await Promise.all([
    api('/tasks'),
    api('/agents'),
    api('/runs'),
    api('/workspaces'),
  ]);

  state.tasks = tasks;
  state.agents = agents;
  state.runs = runs;
  state.workspaces = workspaces;

  if (!state.selectedTaskId && tasks.length) {
    state.selectedTaskId = tasks[0].id;
  }
  if (state.selectedTaskId && !state.tasks.find((task) => task.id === state.selectedTaskId)) {
    state.selectedTaskId = tasks[0]?.id || null;
  }
  if (state.selectedTaskId) {
    await loadMessages(state.selectedTaskId);
    await loadTaskSummary(state.selectedTaskId, true);
  }
  ensureSelectedRun();
  if (state.selectedRunId) {
    await loadRunEvents(state.selectedRunId);
  }
  renderAll();
}

async function selectTask(taskId) {
  state.selectedTaskId = taskId;
  await loadMessages(taskId);
  await loadTaskSummary(taskId, true);
  ensureSelectedRun();
  if (state.selectedRunId) {
    await loadRunEvents(state.selectedRunId);
  }
  renderAll();
}

async function selectRun(runId) {
  state.selectedRunId = runId;
  await loadRunEvents(runId);
  renderAll();
}

function pushEvent(event) {
  state.events.unshift(event);
  state.events = state.events.slice(0, 40);
}

function mergeById(collection, incoming) {
  const index = collection.findIndex((item) => item.id === incoming.id);
  if (index >= 0) {
    collection[index] = incoming;
  } else {
    collection.unshift(incoming);
  }
}

function upsertTaskMessage(taskId, incoming) {
  const list = state.messagesByTask.get(taskId) || [];
  const index = list.findIndex((item) => item.id === incoming.id);
  if (index >= 0) {
    list[index] = incoming;
  } else {
    list.push(incoming);
  }
  list.sort((a, b) => a.created_at - b.created_at);
  state.messagesByTask.set(taskId, list);
}

function appendRunEvent(runEvent) {
  const events = state.runEventsByRun.get(runEvent.run_id) || [];
  const index = events.findIndex((item) => item.id === runEvent.id);
  if (index >= 0) {
    events[index] = runEvent;
  } else {
    events.push(runEvent);
    events.sort((a, b) => a.seq - b.seq);
  }
  state.runEventsByRun.set(runEvent.run_id, events);
}

function handleEvent(message) {
  pushEvent(message);
  const { event, payload } = message;
  if (event === 'task.created' || event === 'task.updated') {
    mergeById(state.tasks, payload);
  }
  if (event === 'task.deleted') {
    state.tasks = state.tasks.filter((task) => task.id !== payload.id);
    state.workspaces = state.workspaces.filter((workspace) => workspace.task_id !== payload.id);
    state.runs = state.runs.filter((run) => run.task_id !== payload.id);
    state.messagesByTask.delete(payload.id);
    state.summariesByTask.delete(payload.id);
    if (state.selectedTaskId === payload.id) {
      state.selectedTaskId = state.tasks[0]?.id || null;
      state.selectedRunId = null;
    }
  }
  if (event === 'task.message_created') {
    upsertTaskMessage(payload.task_id, payload);
    if (payload.task_id === state.selectedTaskId) {
      loadTaskSummary(payload.task_id).then(() => renderTaskDetail()).catch(() => {});
    }
  }
  if (event === 'agent.registered' || event === 'agent.updated') {
    mergeById(state.agents, payload);
  }
  if (event === 'run.created' || event === 'run.updated') {
    mergeById(state.runs, payload);
    if (payload.task_id === state.selectedTaskId) {
      state.selectedRunId = payload.id;
    }
  }
  if (event === 'run.event') {
    appendRunEvent(payload);
  }
  if (event === 'workspace.created') {
    mergeById(state.workspaces, payload);
  }
  ensureSelectedRun();
  renderAll();
}

function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(`${protocol}//${window.location.host}/ws`);

  socket.addEventListener('open', () => {
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
    if (socketRetryTimer) {
      clearTimeout(socketRetryTimer);
      socketRetryTimer = null;
    }
    els.socketBadge.textContent = 'Live';
    els.socketBadge.className = 'tag';
  });

  socket.addEventListener('message', (event) => {
    handleEvent(JSON.parse(event.data));
  });

  socket.addEventListener('close', () => {
    els.socketBadge.textContent = 'Reconnect';
    els.socketBadge.className = 'tag muted';
    if (!refreshTimer) {
      refreshTimer = setInterval(() => {
        refreshData().catch(() => {});
      }, 3000);
    }
    socketRetryTimer = setTimeout(connectWebSocket, 1200);
  });

  socket.addEventListener('error', () => {
    els.socketBadge.textContent = 'Polling';
    els.socketBadge.className = 'tag muted';
    if (!refreshTimer) {
      refreshTimer = setInterval(() => {
        refreshData().catch(() => {});
      }, 3000);
    }
  });
}

async function createWorkspace() {
  const task = getSelectedTask();
  if (!task) return;
  await api(`/tasks/${task.id}/workspace`, { method: 'POST' });
  state.workspaces = await api('/workspaces');
  renderAll();
}

async function refreshSelectedTaskSummary(forceRebuild = false) {
  const task = getSelectedTask();
  if (!task) return;
  if (forceRebuild) {
    const summary = await api(`/tasks/${task.id}/summary/rebuild`, { method: 'POST' });
    state.summariesByTask.set(task.id, summary);
  } else {
    await loadTaskSummary(task.id, true);
  }
  renderTaskDetail();
}

async function updateTaskStatus(status) {
  const task = getSelectedTask();
  if (!task) return;
  const updated = await api(`/tasks/${task.id}`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
  mergeById(state.tasks, updated);
  renderAll();
}

async function deleteSelectedTask() {
  const task = getSelectedTask();
  if (!task) return;
  await api(`/tasks/${task.id}`, { method: 'DELETE' });
  state.tasks = state.tasks.filter((item) => item.id !== task.id);
  state.workspaces = state.workspaces.filter((workspace) => workspace.task_id !== task.id);
  state.runs = state.runs.filter((run) => run.task_id !== task.id);
  state.messagesByTask.delete(task.id);
  state.summariesByTask.delete(task.id);
  state.selectedTaskId = state.tasks[0]?.id || null;
  state.selectedRunId = null;
  if (state.selectedTaskId) {
    await loadMessages(state.selectedTaskId);
    await loadTaskSummary(state.selectedTaskId, true);
    ensureSelectedRun();
    if (state.selectedRunId) {
      await loadRunEvents(state.selectedRunId);
    }
  }
  renderAll();
}

async function ensureWorkspaceIfNeeded() {
  const task = getSelectedTask();
  const workspace = getSelectedWorkspace();
  if (task && task.repo_path && !workspace) {
    await createWorkspace();
  }
}

async function launchAgent(kind, promptOverride = null) {
  const task = getSelectedTask();
  if (!task) return;
  await ensureWorkspaceIfNeeded();
  const prompt = promptOverride || els.launchPrompt.value.trim() || task.summary || `Work on task: ${task.title}`;
  const path = kind === 'codex' ? '/adapters/codex/launch' : '/adapters/claude/launch';
  const payload = kind === 'codex'
    ? { task_id: task.id, prompt, sandbox: 'workspace-write', full_auto: true, skip_git_repo_check: true }
    : { task_id: task.id, prompt, permission_mode: 'default', output_format: 'stream-json', print_mode: true, no_session_persistence: true };
  await api(path, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  state.runs = await api('/runs');
  ensureSelectedRun();
  if (state.selectedRunId) {
    await loadRunEvents(state.selectedRunId);
  }
  renderAll();
}

async function sendTaskMessage() {
  const task = getSelectedTask();
  const content = els.messageInput.value.trim();
  if (!task || !content) return;
  const target = els.messageTarget.value;
  const isBroadcast = target === 'broadcast';
  const messageType = els.messageType.value;
  const message = await api(`/tasks/${task.id}/messages`, {
    method: 'POST',
    body: JSON.stringify({
      sender_type: 'human',
      sender_id: task.created_by || 'human',
      target_type: isBroadcast ? 'broadcast' : 'agent',
      target_id: isBroadcast ? null : target,
      message_type: messageType,
      content,
    }),
  });
  upsertTaskMessage(task.id, message);
  await loadTaskSummary(task.id);
  els.messageInput.value = '';
  renderAll();
  return message;
}

function launchKindFromAgentId(agentId) {
  if (agentId === 'codex_local') return 'codex';
  if (agentId === 'claude_local') return 'claude';
  throw new Error(`Unsupported agent target: ${agentId}`);
}

async function sendMessageAndAskHelper() {
  const target = els.messageTarget.value;
  if (target === 'broadcast') {
    throw new Error('Choose a specific helper first');
  }
  const content = els.messageInput.value.trim();
  if (!content) {
    throw new Error('Write a message first');
  }
  await sendTaskMessage();
  await launchAgent(launchKindFromAgentId(target), content);
}

async function stopSelectedRun() {
  const run = getSelectedRun();
  if (!run || isTerminalRunStatus(run.status)) return;
  await api(`/runs/${run.id}/stop`, {
    method: 'POST',
  });
  state.runs = await api('/runs');
  await loadRunEvents(run.id);
  renderAll();
}

function buildTransferContent(message, mode = 'full') {
  if (mode === 'summary') {
    return [
      'Key conclusion prepared by Multy-Bt:',
      summarizeForTransfer(message.content),
    ].join('\n');
  }
  return message.content;
}

async function handoffMessage(message, toAgentId, note = '', mode = 'full') {
  const task = getSelectedTask();
  if (!task) return;
  const transferContent = buildTransferContent(message, mode);
  const handoff = await api(`/tasks/${task.id}/handoff`, {
    method: 'POST',
    body: JSON.stringify({
      from_agent_id: message.sender_id,
      to_agent_id: toAgentId,
      content: transferContent,
      note: note || null,
    }),
  });
  await loadMessages(task.id);
  await loadTaskSummary(task.id);
  await launchAgent(launchKindFromAgentId(toAgentId), handoff.content);
}

els.taskForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = new FormData(els.taskForm);
  const payload = {
    title: form.get('title'),
    summary: form.get('summary'),
    repo_path: form.get('repo_path') || null,
    created_by: form.get('created_by'),
    priority: form.get('priority'),
  };
  const task = await api('/tasks', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  els.taskForm.reset();
  document.getElementById('taskCreatedBy').value = 'cloudwl';
  document.getElementById('taskPriority').value = 'normal';
  state.selectedTaskId = task.id;
  state.selectedRunId = null;
  await refreshData();
});

els.createWorkspaceBtn.addEventListener('click', async () => {
  try {
    await createWorkspace();
  } catch (error) {
    alert(`Prepare safe copy failed: ${error.message}`);
  }
});

els.launchCodexBtn.addEventListener('click', async () => {
  try {
    els.agentPicker.value = 'codex';
    await launchAgent('codex');
  } catch (error) {
    alert(`Ask Codex failed: ${error.message}`);
  }
});

els.launchClaudeBtn.addEventListener('click', async () => {
  try {
    els.agentPicker.value = 'claude';
    await launchAgent('claude');
  } catch (error) {
    alert(`Ask Claude failed: ${error.message}`);
  }
});

els.sendTaskBtn.addEventListener('click', async () => {
  try {
    await launchAgent(els.agentPicker.value);
  } catch (error) {
    alert(`Send task failed: ${error.message}`);
  }
});

els.sendMessageBtn.addEventListener('click', async () => {
  try {
    await sendTaskMessage();
  } catch (error) {
    alert(`Send message failed: ${error.message}`);
  }
});

els.sendAndAskBtn.addEventListener('click', async () => {
  try {
    await sendMessageAndAskHelper();
  } catch (error) {
    alert(`Send and ask failed: ${error.message}`);
  }
});

els.runEventFilter.addEventListener('change', () => {
  renderRunDetail();
});

els.messageTarget.addEventListener('change', () => {
  updateActionState();
});

els.stopRunBtn.addEventListener('click', async () => {
  try {
    await stopSelectedRun();
  } catch (error) {
    alert(`Stop activity failed: ${error.message}`);
  }
});

els.refreshAllBtn.addEventListener('click', async () => {
  try {
    await refreshData();
  } catch (error) {
    alert(`Refresh failed: ${error.message}`);
  }
});

els.workflowHelpBtn.addEventListener('click', () => {
  els.workflowDialog.showModal();
});

els.closeWorkflowHelpBtn.addEventListener('click', () => {
  els.workflowDialog.close();
});

els.workflowDialog.addEventListener('click', (event) => {
  const rect = els.workflowDialog.getBoundingClientRect();
  const inside =
    event.clientX >= rect.left &&
    event.clientX <= rect.right &&
    event.clientY >= rect.top &&
    event.clientY <= rect.bottom;
  if (!inside) {
    els.workflowDialog.close();
  }
});

els.deleteTaskBtn.addEventListener('click', async () => {
  const task = getSelectedTask();
  if (!task) return;
  const confirmed = window.confirm(
    `Remove task "${task.title}" from Multy-Bt?\n\nThis only deletes the task record, messages, runs, and saved memory inside Multy-Bt. It does not delete your project folder or repository.`
  );
  if (!confirmed) return;
  try {
    await deleteSelectedTask();
  } catch (error) {
    alert(`Remove task failed: ${error.message}`);
  }
});

els.refreshSummaryBtn.addEventListener('click', async () => {
  try {
    await refreshSelectedTaskSummary(true);
  } catch (error) {
    alert(`Refresh memory failed: ${error.message}`);
  }
});

for (const button of els.taskStatusFlow.querySelectorAll('[data-status]')) {
  button.addEventListener('click', async () => {
    try {
      await updateTaskStatus(button.dataset.status);
    } catch (error) {
      alert(`Update task stage failed: ${error.message}`);
    }
  });
}

(async function init() {
  try {
    await refreshData();
    connectWebSocket();
  } catch (error) {
    pushEvent({ event: 'ui.error', payload: { message: error.message }, timestamp: Date.now() });
    renderAll();
  }
})();

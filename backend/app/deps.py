from app.core.events import EventBus
from app.core.runner import AgentRunManager
from app.core.store import SQLiteStore
from app.core.workspaces import WorkspaceManager

store = SQLiteStore()
events = EventBus()
workspace_manager = WorkspaceManager(store, events)
runner = AgentRunManager(store, events, workspace_manager=workspace_manager)

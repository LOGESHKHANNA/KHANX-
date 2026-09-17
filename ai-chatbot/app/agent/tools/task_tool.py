"""
TaskManagerTool for KHANX agentic framework.

Allows users to manage personal tasks via chat:
- CREATE: Add a new task (title, description, priority)
- VIEW: List user's tasks (filtered by status: pending, completed, all)
- UPDATE: Modify task title, description, priority, or status
- COMPLETE: Mark task status as completed
- DELETE: Remove a task by ID or title

Security: Strictly isolated per user_id. Users can never view or modify another user's tasks.
"""

from typing import Any, Optional
from app.agent.tools.base import BaseTool
from app.agent.task_manager import task_manager_engine


class TaskManagerTool(BaseTool):
    """Tool for KHANX to manage personal user tasks through chat."""

    name = "manage_tasks"
    description = (
        "Create, view, update, complete, or delete personal user tasks. "
        "Actions: 'create', 'view', 'update', 'complete', 'delete'. "
        "Use 'create' to add a new task. Use 'view' to list tasks. "
        "Use 'complete' to mark a task as done. Use 'delete' to remove a task."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "view", "update", "complete", "delete"],
                "description": "Task action: 'create', 'view', 'update', 'complete', or 'delete'."
            },
            "title": {
                "type": "string",
                "description": "Task title (required for 'create')."
            },
            "description": {
                "type": "string",
                "description": "Optional task description or details."
            },
            "task_id": {
                "type": "string",
                "description": "Task ID or title identifier for 'update', 'complete', or 'delete'."
            },
            "status_filter": {
                "type": "string",
                "enum": ["pending", "completed", "all"],
                "description": "Filter tasks for 'view' action: 'pending' (default), 'completed', or 'all'."
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Task priority level: 'low', 'medium', or 'high'."
            }
        },
        "required": ["action"]
    }
    is_sensitive = False
    risk_level = "LOW"

    async def execute(
        self,
        action: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        task_id: Optional[str] = None,
        status_filter: Optional[str] = "pending",
        priority: Optional[str] = "medium",
        db: Optional[Any] = None,
        user_id: Optional[str] = None,
        **kwargs: Any
    ) -> str:
        """Execute a task manager action."""
        if not user_id:
            return "Task Manager unavailable: No authenticated user context."

        try:
            act = action.strip().lower()

            # ── CREATE ───────────────────────────────────────────────────────
            if act == "create":
                if not title or not title.strip():
                    return "Task creation requires a task 'title'."
                task = await task_manager_engine.create_task(
                    user_id=user_id,
                    title=title,
                    description=description,
                    priority=priority or "medium",
                    db=db
                )
                return f"✅ Task Created [ID: {task['id']}]: **{task['title']}** (Priority: {task['priority'].upper()})."

            # ── VIEW / LIST ──────────────────────────────────────────────────
            elif act == "view":
                tasks = await task_manager_engine.list_tasks(
                    user_id=user_id,
                    status_filter=status_filter or "pending",
                    db=db
                )
                if not tasks:
                    filter_label = status_filter if status_filter else "pending"
                    return f"No {filter_label} tasks found."

                lines = [f"### 📋 Your Tasks ({status_filter or 'pending'}):"]
                for t in tasks:
                    status_icon = "✅" if t.get("status") == "completed" else "⏳"
                    prio = t.get("priority", "medium").upper()
                    desc_str = f" — *{t['description']}*" if t.get("description") else ""
                    lines.append(f"- {status_icon} **[ID: {t['id']}]** `{t['title']}` ({prio}){desc_str}")

                return "\n".join(lines)

            # ── COMPLETE ─────────────────────────────────────────────────────
            elif act == "complete":
                target = task_id or title
                if not target:
                    return "Completing a task requires a 'task_id' or task title."
                updated = await task_manager_engine.complete_task(
                    user_id=user_id,
                    task_id_or_title=target,
                    db=db
                )
                if updated:
                    return f"✅ Task Completed [ID: {updated['id']}]: **{updated['title']}**."
                return f"Task '{target}' not found."

            # ── UPDATE ───────────────────────────────────────────────────────
            elif act == "update":
                target = task_id or title
                if not target:
                    return "Updating a task requires a 'task_id' or task title."
                updated = await task_manager_engine.update_task(
                    user_id=user_id,
                    task_id_or_title=target,
                    title=title if (title and title != target) else None,
                    description=description,
                    priority=priority,
                    db=db
                )
                if updated:
                    return f"✅ Task Updated [ID: {updated['id']}]: **{updated['title']}** (Status: {updated['status']}, Priority: {updated['priority'].upper()})."
                return f"Task '{target}' not found."

            # ── DELETE ───────────────────────────────────────────────────────
            elif act == "delete":
                target = task_id or title
                if not target:
                    return "Deleting a task requires a 'task_id' or task title."
                deleted = await task_manager_engine.delete_task(
                    user_id=user_id,
                    task_id_or_title=target,
                    db=db
                )
                if deleted:
                    return f"✅ Task '{target}' deleted successfully."
                return f"Task '{target}' not found."

            else:
                return f"Unknown task action '{act}'. Use 'create', 'view', 'update', 'complete', or 'delete'."

        except Exception as e:
            return f"[Task Manager temporary warning: {str(e)}. Proceeding with standard response.]"

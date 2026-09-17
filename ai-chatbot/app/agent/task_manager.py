"""
KHANX Per-User Task Manager Engine.

Allows users to create, view, update, complete, and delete personal tasks via chat.

Security & Multi-Tenancy:
- All task operations are strictly filtered by user_id.
- Users can never view, update, or delete another user's tasks.

Database & Persistence:
- Primary: Supabase DB table `user_tasks` (or `tasks`).
- Fallback: In-memory per-user fallback store if DB is offline.
"""

import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any


class TaskManagerEngine:
    """Per-user task storage and CRUD manager."""

    def __init__(self):
        # Fallback per-user task store if DB table is unavailable
        self._fallback_store: Dict[str, List[Dict[str, Any]]] = {}

    def _get_user_fallback(self, user_id: str) -> List[Dict[str, Any]]:
        if user_id not in self._fallback_store:
            self._fallback_store[user_id] = []
        return self._fallback_store[user_id]

    async def create_task(
        self,
        user_id: str,
        title: str,
        description: Optional[str] = None,
        priority: str = "medium",
        db: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Create a new task for an authenticated user."""
        task_id = str(uuid.uuid4())[:8]
        now = datetime.utcnow().isoformat()
        task_data = {
            "id": task_id,
            "user_id": user_id,
            "title": title.strip(),
            "description": (description or "").strip(),
            "status": "pending",
            "priority": priority.lower() if priority else "medium",
            "created_at": now,
            "updated_at": now
        }

        # Try Supabase DB first
        if db:
            try:
                res = db.table("user_tasks").insert(task_data).execute()
                if res.data:
                    return res.data[0]
            except Exception as e:
                print(f"Supabase task insert warning (using fallback): {e}")

        # Fallback in-memory store
        tasks = self._get_user_fallback(user_id)
        tasks.append(task_data)
        return task_data

    async def list_tasks(
        self,
        user_id: str,
        status_filter: Optional[str] = None,
        db: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """List tasks for a specific user, strictly filtered by user_id."""
        if db:
            try:
                query = db.table("user_tasks").select("*").eq("user_id", user_id)
                if status_filter and status_filter.lower() != "all":
                    query = query.eq("status", status_filter.lower())
                res = query.order("created_at", desc=True).execute()
                if res.data is not None:
                    return res.data
            except Exception as e:
                print(f"Supabase task select warning (using fallback): {e}")

        # Fallback in-memory store
        tasks = self._get_user_fallback(user_id)
        if status_filter and status_filter.lower() != "all":
            tasks = [t for t in tasks if t.get("status") == status_filter.lower()]
        return sorted(tasks, key=lambda x: x.get("created_at", ""), reverse=True)

    async def update_task(
        self,
        user_id: str,
        task_id_or_title: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        db: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Update a task for an authenticated user."""
        target = task_id_or_title.strip().lower()
        now = datetime.utcnow().isoformat()

        updates: Dict[str, Any] = {"updated_at": now}
        if title:
            updates["title"] = title.strip()
        if description is not None:
            updates["description"] = description.strip()
        if status:
            updates["status"] = status.strip().lower()
        if priority:
            updates["priority"] = priority.strip().lower()

        if db:
            try:
                # Scoped strictly by user_id
                res = db.table("user_tasks").update(updates).eq("user_id", user_id).eq("id", target).execute()
                if res.data:
                    return res.data[0]
                # Try by title match if ID didn't match
                res_title = db.table("user_tasks").update(updates).eq("user_id", user_id).ilike("title", f"%{target}%").execute()
                if res_title.data:
                    return res_title.data[0]
            except Exception as e:
                print(f"Supabase task update warning (using fallback): {e}")

        # Fallback
        tasks = self._get_user_fallback(user_id)
        for t in tasks:
            if t["id"].lower() == target or target in t["title"].lower():
                t.update(updates)
                return t
        return None

    async def complete_task(
        self,
        user_id: str,
        task_id_or_title: str,
        db: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Mark a task as completed for an authenticated user."""
        return await self.update_task(user_id=user_id, task_id_or_title=task_id_or_title, status="completed", db=db)

    async def delete_task(
        self,
        user_id: str,
        task_id_or_title: str,
        db: Optional[Any] = None
    ) -> bool:
        """Delete a task belonging strictly to user_id."""
        target = task_id_or_title.strip().lower()

        if db:
            try:
                # Delete by ID first
                res = db.table("user_tasks").delete().eq("user_id", user_id).eq("id", target).execute()
                if res.data:
                    return True
                # Delete by title match
                res_title = db.table("user_tasks").delete().eq("user_id", user_id).ilike("title", f"%{target}%").execute()
                if res_title.data:
                    return True
            except Exception as e:
                print(f"Supabase task delete warning (using fallback): {e}")

        # Fallback
        tasks = self._get_user_fallback(user_id)
        for i, t in enumerate(tasks):
            if t["id"].lower() == target or target in t["title"].lower():
                tasks.pop(i)
                return True
        return False


# Singleton
task_manager_engine = TaskManagerEngine()

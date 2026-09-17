import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.agent.memory.base import BaseMemory

class EpisodicMemory(BaseMemory):
    """Stores session summaries of completed conversations to allow multi-session continuity."""

    def __init__(self, data_dir: str = "data/episodic"):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)

    def _get_local_filepath(self, user_id: str) -> str:
        safe_user_id = "".join(c for c in user_id if c.isalnum() or c in ("-", "_"))
        return os.path.join(self.data_dir, f"{safe_user_id}.json")

    def _read_local_summaries(self, user_id: str) -> List[Dict[str, Any]]:
        path = self._get_local_filepath(user_id)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error reading local episodic memory for {user_id}: {e}")
        return []

    def _write_local_summaries(self, user_id: str, summaries: List[Dict[str, Any]]) -> None:
        path = self._get_local_filepath(user_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(summaries, f, indent=2)
        except Exception as e:
            print(f"Error writing local episodic memory for {user_id}: {e}")

    async def get_context(self, user_id: str, query: str, db: Optional[Any] = None) -> Optional[str]:
        """Retrieve relevant past session summaries if user asks about past topics or continuing work."""
        query_lower = query.lower()

        # Keywords indicating past session recall request
        past_keywords = ["yesterday", "last session", "previous chat", "continue", "stopped", "last time", "where were we", "we worked on", "past chat"]
        is_past_recall = any(kw in query_lower for kw in past_keywords)

        summaries = await self.get_all_summaries(user_id, db=db)
        if not summaries:
            return None

        if is_past_recall or len(summaries) <= 3:
            recent = summaries[-3:]
            lines = [f"- Session '{s.get('title', 'Previous Chat')}': {s['summary']}" for s in reversed(recent)]
            return "\n".join(lines)

        # Keyword matching across session summaries
        query_words = {w.lower() for w in query.split() if len(w) > 2}
        relevant = []
        for s in summaries:
            summary_text = s.get("summary", "").lower()
            title = s.get("title", "").lower()
            overlap = len(query_words & (set(summary_text.split()) | set(title.split())))
            if overlap > 0:
                relevant.append(s)

        if not relevant:
            return None

        lines = [f"- Session '{s.get('title', 'Chat')}': {s['summary']}" for s in relevant[-3:]]
        return "\n".join(lines)

    async def get_all_summaries(self, user_id: str, db: Optional[Any] = None) -> List[Dict[str, Any]]:
        """Retrieve all session summaries for user."""
        if db:
            try:
                res = db.table("session_summaries").select("*").eq("user_id", user_id).order("updated_at", desc=True).execute()
                if res.data is not None:
                    return res.data
            except Exception:
                pass

        return self._read_local_summaries(user_id)

    async def save_session_summary(
        self,
        user_id: str,
        session_id: str,
        summary: str,
        title: Optional[str] = "Chat Session",
        db: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Save or update summary for a given session."""
        now_str = datetime.now(timezone.utc).isoformat()
        summary_item = {
            "user_id": user_id,
            "session_id": session_id,
            "title": title,
            "summary": summary,
            "updated_at": now_str
        }

        if db:
            try:
                existing = db.table("session_summaries").select("id").eq("session_id", session_id).execute()
                if existing.data:
                    res = db.table("session_summaries").update({
                        "summary": summary,
                        "title": title,
                        "updated_at": now_str
                    }).eq("session_id", session_id).execute()
                    if res.data:
                        return res.data[0]
                else:
                    res = db.table("session_summaries").insert(summary_item).execute()
                    if res.data:
                        return res.data[0]
            except Exception as db_err:
                print(f"Supabase session_summaries save warning: {db_err}")

        # Local JSON fallback
        local_items = self._read_local_summaries(user_id)
        updated = False
        for item in local_items:
            if item.get("session_id") == session_id:
                item["summary"] = summary
                item["title"] = title
                item["updated_at"] = now_str
                summary_item = item
                updated = True
                break

        if not updated:
            summary_item["id"] = f"ep_{int(datetime.now().timestamp()*1000)}"
            summary_item["created_at"] = now_str
            local_items.append(summary_item)

        self._write_local_summaries(user_id, local_items)
        return summary_item

    async def delete_session_summary(self, user_id: str, session_id: str, db: Optional[Any] = None) -> bool:
        """Delete episodic summary for a specific session."""
        deleted = False

        if db:
            try:
                db.table("session_summaries").delete().eq("user_id", user_id).eq("session_id", session_id).execute()
                deleted = True
            except Exception:
                pass

        local_items = self._read_local_summaries(user_id)
        filtered = [s for s in local_items if s.get("session_id") != session_id]
        if len(filtered) < len(local_items):
            self._write_local_summaries(user_id, filtered)
            deleted = True

        return deleted

    async def clear_all(self, user_id: str, db: Optional[Any] = None) -> bool:
        """Clear all episodic session summaries for user."""
        if db:
            try:
                db.table("session_summaries").delete().eq("user_id", user_id).execute()
            except Exception:
                pass

        self._write_local_summaries(user_id, [])
        return True

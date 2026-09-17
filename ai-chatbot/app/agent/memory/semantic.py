import os
import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.agent.memory.base import BaseMemory

# Regex patterns to detect secret credentials (API keys, JWTs, passwords, auth tokens)
SECRET_PATTERNS = [
    re.compile(r"gsk_[A-Za-z0-9_\-]{20,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}", re.IGNORECASE),
    re.compile(r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}", re.IGNORECASE),  # JWT tokens
    re.compile(r"(password|passwd|secret|api_key|token)\s*[:=]\s*\S+", re.IGNORECASE),
]

def is_safe_memory(key: str, value: str) -> bool:
    """Validate that key and value do not contain private credentials or secrets."""
    combined = f"{key} {value}"
    for pat in SECRET_PATTERNS:
        if pat.search(combined):
            return False
    return True

class SemanticMemory(BaseMemory):
    """Stores and retrieves long-term facts and user preferences with secret shielding and DB/JSON dual persistence."""

    def __init__(self, data_dir: str = "data/memories"):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)

    def _get_local_filepath(self, user_id: str) -> str:
        safe_user_id = "".join(c for c in user_id if c.isalnum() or c in ("-", "_"))
        return os.path.join(self.data_dir, f"{safe_user_id}.json")

    def _read_local_memories(self, user_id: str) -> List[Dict[str, Any]]:
        path = self._get_local_filepath(user_id)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error reading local memory for {user_id}: {e}")
        return []

    def _write_local_memories(self, user_id: str, memories: List[Dict[str, Any]]) -> None:
        path = self._get_local_filepath(user_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(memories, f, indent=2)
        except Exception as e:
            print(f"Error writing local memory for {user_id}: {e}")

    async def get_context(self, user_id: str, query: str, db: Optional[Any] = None) -> Optional[str]:
        """Retrieve relevant semantic memories for query."""
        all_memories = await self.get_all_memories(user_id, db=db)
        if not all_memories:
            return None

        query_words = {w.lower() for w in query.split() if len(w) > 2}
        relevant = []

        for m in all_memories:
            k = m.get("key", "").lower()
            v = m.get("value", "").lower()
            cat = m.get("category", "").lower()

            # Relevance scoring based on word overlap or query matching preference keywords
            match_score = len(query_words & (set(k.split()) | set(v.split()) | set(cat.split())))
            if match_score > 0 or any(kw in query.lower() for kw in ["prefer", "style", "profile", "setting", "like", "using", "work", "always", "who am i", "my"]):
                relevant.append(m)

        if not relevant and len(all_memories) <= 5:
            relevant = all_memories  # Include user facts if set is small and user asks general question

        if not relevant:
            return None

        lines = [f"- {m['key']}: {m['value']}" for m in relevant]
        return "\n".join(lines)

    async def get_all_memories(self, user_id: str, db: Optional[Any] = None) -> List[Dict[str, Any]]:
        """Fetch all semantic memories for user (Supabase with JSON fallback)."""
        if db:
            try:
                res = db.table("user_memories").select("*").eq("user_id", user_id).execute()
                if res.data is not None:
                    return res.data
            except Exception:
                pass  # Fall back to local JSON store if Supabase table doesn't exist yet

        return self._read_local_memories(user_id)

    async def set_memory(
        self,
        user_id: str,
        key: str,
        value: str,
        category: str = "preference",
        db: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Store or update a user semantic fact/preference after secret safety verification."""
        if not is_safe_memory(key, value):
            raise ValueError("Memory rejection: Secret credentials, API keys, or private tokens cannot be stored in memory.")

        now_str = datetime.now(timezone.utc).isoformat()
        memory_item = {
            "user_id": user_id,
            "key": key,
            "value": value,
            "category": category,
            "updated_at": now_str,
        }

        # 1. Update Supabase if available
        if db:
            try:
                # Check existing
                existing = db.table("user_memories").select("id").eq("user_id", user_id).eq("key", key).execute()
                if existing.data:
                    res = db.table("user_memories").update({
                        "value": value,
                        "category": category,
                        "updated_at": now_str
                    }).eq("id", existing.data[0]["id"]).execute()
                    if res.data:
                        return res.data[0]
                else:
                    res = db.table("user_memories").insert(memory_item).execute()
                    if res.data:
                        return res.data[0]
            except Exception as db_err:
                print(f"Supabase user_memories save warning (using local fallback): {db_err}")

        # 2. Local JSON store fallback
        local_items = self._read_local_memories(user_id)
        updated = False
        for item in local_items:
            if item.get("key") == key:
                item["value"] = value
                item["category"] = category
                item["updated_at"] = now_str
                updated = True
                memory_item = item
                break

        if not updated:
            memory_item["id"] = f"mem_{int(datetime.now().timestamp()*1000)}"
            memory_item["created_at"] = now_str
            local_items.append(memory_item)

        self._write_local_memories(user_id, local_items)
        return memory_item

    async def delete_memory(self, user_id: str, key_or_id: str, db: Optional[Any] = None) -> bool:
        """Delete a specific semantic memory item by key or ID."""
        deleted = False

        if db:
            try:
                db.table("user_memories").delete().eq("user_id", user_id).eq("key", key_or_id).execute()
                db.table("user_memories").delete().eq("user_id", user_id).eq("id", key_or_id).execute()
                deleted = True
            except Exception:
                pass

        local_items = self._read_local_memories(user_id)
        initial_len = len(local_items)
        filtered = [m for m in local_items if m.get("key") != key_or_id and m.get("id") != key_or_id]

        if len(filtered) < initial_len:
            self._write_local_memories(user_id, filtered)
            deleted = True

        return deleted

    async def clear_all(self, user_id: str, db: Optional[Any] = None) -> bool:
        """Clear all semantic memories for user."""
        if db:
            try:
                db.table("user_memories").delete().eq("user_id", user_id).execute()
            except Exception:
                pass

        self._write_local_memories(user_id, [])
        return True

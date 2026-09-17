"""
Long-Term Memory Tool for KHANX agentic framework.

Allows the KHANX agent to:
- SAVE: Store user preferences, project context, and session information
- RECALL: Retrieve previously saved memories
- DELETE: Remove a specific memory by key at the user's request

Security: Automatically blocks storage of secrets, passwords, API keys, and tokens.
Availability: Falls back gracefully if DB is unavailable — existing chat is unaffected.
"""
from typing import Any, Optional
from app.agent.tools.base import BaseTool


class LongTermMemoryTool(BaseTool):
    """Tool for KHANX to save, recall, and delete long-term user memory facts."""

    name = "long_term_memory"
    description = (
        "Manage user long-term memory. Actions: "
        "'save' (store a preference/fact), 'recall' (retrieve memories), 'delete' (remove a memory by key). "
        "Use 'save' to remember important user preferences, project context, or goals across sessions. "
        "Use 'recall' to retrieve what you know about the user. "
        "NEVER save passwords, API keys, tokens, or any credentials."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["save", "recall", "delete"],
                "description": "Memory action: 'save', 'recall', or 'delete'."
            },
            "key": {
                "type": "string",
                "description": "Memory key (e.g. 'preferred_language', 'current_project', 'coding_style')."
            },
            "value": {
                "type": "string",
                "description": "Memory value — required for 'save' action only."
            },
            "category": {
                "type": "string",
                "description": "Category: 'preference', 'project_context', or 'session_info'.",
                "enum": ["preference", "project_context", "session_info"]
            }
        },
        "required": ["action"]
    }
    is_sensitive = False
    risk_level = "LOW"

    async def execute(
        self,
        action: str,
        key: Optional[str] = None,
        value: Optional[str] = None,
        category: Optional[str] = "preference",
        db: Optional[Any] = None,
        user_id: Optional[str] = None,
        **kwargs: Any
    ) -> str:
        """Execute a memory action: save, recall, or delete."""
        if not user_id:
            return "Memory unavailable: No authenticated user context."

        try:
            from app.agent.memory.manager import memory_manager

            # ── SAVE ─────────────────────────────────────────────────────────
            if action == "save":
                if not key or not value:
                    return "Memory save requires both 'key' and 'value'."
                result = await memory_manager.add_semantic_fact(
                    user_id=user_id,
                    key=key.strip(),
                    value=value.strip(),
                    category=category or "preference",
                    db=db
                )
                return f"✅ Memory saved: '{key}' = '{value}' (category: {category})."

            # ── RECALL ────────────────────────────────────────────────────────
            elif action == "recall":
                from app.agent.memory.manager import memory_manager
                all_mem = await memory_manager.get_user_memories(user_id=user_id, db=db)
                facts = all_mem.get("semantic_memories", [])
                if not facts:
                    return "No long-term memories found for this user yet."
                # If a key is specified, filter to it
                if key:
                    facts = [f for f in facts if key.lower() in f.get("key", "").lower()]
                    if not facts:
                        return f"No memory found for key '{key}'."
                lines = [f"- [{f.get('category','?')}] {f.get('key','?')}: {f.get('value','?')}" for f in facts[:20]]
                return "User Long-Term Memory:\n" + "\n".join(lines)

            # ── DELETE ────────────────────────────────────────────────────────
            elif action == "delete":
                if not key:
                    return "Memory delete requires a 'key' to identify which memory to remove."
                success = await memory_manager.delete_semantic_fact(
                    user_id=user_id,
                    key_or_id=key.strip(),
                    db=db
                )
                if success:
                    return f"✅ Memory '{key}' deleted."
                return f"Memory key '{key}' not found."

            else:
                return f"Unknown memory action '{action}'. Use 'save', 'recall', or 'delete'."

        except ValueError as ve:
            # Secret-rejection from security layer
            return f"⚠️ Memory rejected: {str(ve)}"
        except Exception as e:
            return f"[Long-term memory unavailable: {str(e)}. Continuing without memory.]"

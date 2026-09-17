from typing import Any, Dict
from app.agent.tools.base import BaseTool
from app.agent.memory import memory_manager

class DeleteUserMemoryTool(BaseTool):
    name = "delete_user_memory"
    description = "Delete a specific long-term user memory or preference. Requires human approval."
    is_sensitive = True
    risk_level = "HIGH"
    parameters = {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "The key or title of the memory item to delete"}
        },
        "required": ["key"]
    }

    async def execute(self, key: str, user_id: str, db: Any = None, **kwargs: Any) -> str:
        deleted = await memory_manager.delete_semantic_fact(user_id=user_id, key_or_id=key, db=db)
        if deleted:
            return f"Successfully deleted user memory fact '{key}'."
        return f"User memory fact '{key}' was not found."

class ModifyUserDataTool(BaseTool):
    name = "modify_user_data"
    description = "Modify or update user account preferences or data records. Requires human approval."
    is_sensitive = True
    risk_level = "CRITICAL"
    parameters = {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "The data field to update"},
            "value": {"type": "string", "description": "The new value for the field"}
        },
        "required": ["key", "value"]
    }

    async def execute(self, key: str, value: str, user_id: str, db: Any = None, **kwargs: Any) -> str:
        updated = await memory_manager.add_semantic_fact(user_id=user_id, key=key, value=value, db=db)
        return f"Successfully modified user data '{key}' to '{value}'."

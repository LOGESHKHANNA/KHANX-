from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseMemory(ABC):
    """Abstract base class for memory layers in KHANX agent system."""

    @abstractmethod
    async def get_context(self, user_id: str, query: str, **kwargs: Any) -> Optional[str]:
        """Retrieve relevant memory string context for the given user query."""
        pass

from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseTool(ABC):
    """Abstract base class for all modular KHANX agent tools."""
    name: str
    description: str
    parameters: Dict[str, Any]
    is_sensitive: bool = False
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Execute tool logic asynchronously and return result string or dict."""
        pass

    def to_schema(self) -> Dict[str, Any]:
        """Return OpenAI/Groq function tool definition schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }

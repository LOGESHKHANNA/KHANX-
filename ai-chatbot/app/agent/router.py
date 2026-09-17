from app.agent.state import AgentState
from typing import Optional

class AgentRouter:
    """Classifies user message intent and determines if agent tool execution is required."""

    def classify_intent(self, state: AgentState) -> Optional[str]:
        """Classify user intent. Returns None if query should fall back to standard Chat/RAG."""
        # Baseline router fallback — currently delegates all standard chat/rag requests to default pipeline
        return None

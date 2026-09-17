from typing import List, Dict, Any, Optional
from app.agent.memory.short_term import ShortTermMemory
from app.agent.memory.semantic import SemanticMemory
from app.agent.memory.episodic import EpisodicMemory

class MemoryManager:
    """Central orchestrator managing Short-Term, Semantic, and Episodic memory layers."""

    def __init__(self):
        self.short_term = ShortTermMemory(max_history_turns=8)
        self.semantic = SemanticMemory()
        self.episodic = EpisodicMemory()

    async def get_memory_context(
        self,
        user_id: str,
        query: str,
        db: Optional[Any] = None
    ) -> Optional[str]:
        """Selective memory retrieval based on query relevance."""
        if not user_id:
            return None

        sections = []

        # 1. Semantic memory context (user facts & preferences)
        semantic_ctx = await self.semantic.get_context(user_id=user_id, query=query, db=db)
        if semantic_ctx:
            sections.append(f"--- USER PREFERENCES & FACTS ---\n{semantic_ctx}")

        # 2. Episodic memory context (past sessions)
        episodic_ctx = await self.episodic.get_context(user_id=user_id, query=query, db=db)
        if episodic_ctx:
            sections.append(f"--- PAST SESSION SUMMARIES ---\n{episodic_ctx}")

        if not sections:
            return None

        return "\n\n".join(sections)

    async def get_user_memories(self, user_id: str, db: Optional[Any] = None) -> Dict[str, Any]:
        """Fetch all user memories across semantic and episodic layers."""
        sem = await self.semantic.get_all_memories(user_id, db=db)
        ep = await self.episodic.get_all_summaries(user_id, db=db)
        return {
            "user_id": user_id,
            "semantic_memories": sem,
            "episodic_summaries": ep,
        }

    async def add_semantic_fact(
        self,
        user_id: str,
        key: str,
        value: str,
        category: str = "preference",
        db: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Store or update user long-term fact after secret validation."""
        return await self.semantic.set_memory(user_id, key, value, category=category, db=db)

    async def delete_semantic_fact(self, user_id: str, key_or_id: str, db: Optional[Any] = None) -> bool:
        """Delete specific semantic fact."""
        return await self.semantic.delete_memory(user_id, key_or_id, db=db)

    async def delete_session_episodic(self, user_id: str, session_id: str, db: Optional[Any] = None) -> bool:
        """Clear memory for a specific session."""
        return await self.episodic.delete_session_summary(user_id, session_id, db=db)

    async def clear_all_user_memories(self, user_id: str, db: Optional[Any] = None) -> bool:
        """Clear all memories for user across semantic and episodic layers."""
        res_sem = await self.semantic.clear_all(user_id, db=db)
        res_ep = await self.episodic.clear_all(user_id, db=db)
        return res_sem and res_ep

# Singleton instance
memory_manager = MemoryManager()

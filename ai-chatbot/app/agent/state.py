"""
Structured agent state for the KHANX stateful workflow graph.
Uses TypedDict for compatibility with graph node functions.
"""
from typing import TypedDict, List, Dict, Any, Optional


class ToolCallRecord(TypedDict, total=False):
    """Record of a single tool invocation."""
    tool_name: str
    tool_args: Dict[str, Any]
    tool_result: str
    success: bool


class AgentState(TypedDict, total=False):
    """Full execution state passed through the agent workflow graph.

    Every node reads from and writes partial updates back to this state.
    """
    # ── User & session context ────────────────────────────────────────────
    user_message: str
    mode: str               # "chat" | "rag"
    user_id: Optional[str]
    session_id: Optional[str]
    db: Any                  # Supabase authed client (not serialised)

    # ── Conversation messages (OpenAI/Groq format) ────────────────────────
    messages: List[Dict[str, Any]]

    # ── Routing ───────────────────────────────────────────────────────────
    route: Optional[str]     # "rag" | "calculator" | "web_search" | "wikipedia" | "general_llm"

    # ── Tool execution tracking ───────────────────────────────────────────
    tool_calls: List[ToolCallRecord]
    tool_results: List[str]
    retrieved_docs: Optional[str]      # RAG context text

    # ── Loop control ──────────────────────────────────────────────────────
    iteration_count: int
    max_iterations: int      # configurable cap (default 5)
    needs_more_tools: bool   # set by process_tool_result node

    # ── Outcome ───────────────────────────────────────────────────────────
    final_response: Optional[str]
    is_complete: bool
    errors: List[str]


def create_initial_state(
    user_message: str,
    messages: List[Dict[str, Any]],
    mode: str = "chat",
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    db: Any = None,
    max_iterations: int = 5,
) -> AgentState:
    """Factory for a clean initial state dict."""
    return AgentState(
        user_message=user_message,
        mode=mode,
        user_id=user_id,
        session_id=session_id,
        db=db,
        messages=list(messages),
        route=None,
        tool_calls=[],
        tool_results=[],
        retrieved_docs=None,
        iteration_count=0,
        max_iterations=max_iterations,
        needs_more_tools=False,
        final_response=None,
        is_complete=False,
        errors=[],
    )

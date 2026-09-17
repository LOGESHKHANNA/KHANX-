"""
Node functions for the KHANX stateful agent graph.
Each node receives the mutable ``state`` dict, may perform async work, and returns a dict optionally containing ``next_node``.
"""
import json
from typing import Dict, Any

from app.agent.tools.registry import tool_registry
from app.agent.state import AgentState

# Helper to append a message to the LLM conversation list
def _append_message(state: Dict[str, Any], role: str, content: str):
    if "messages" not in state:
        state["messages"] = []
    state["messages"].append({"role": role, "content": content})


async def route_request_node(state: Dict[str, Any]):
    """LLM‑based intent classification.

    Sends a short system prompt + the user message to Groq asking for one of the
    predefined route identifiers. The response is stored in ``state["route"]``.
    """
    from app.core.config import settings
    from app.services.groq_retry import call_groq_with_retry
    import groq

    # Build a minimal classification prompt – no token waste
    system = "You are a router. Classify the user's request into one of: rag, calculator, web_search, wikipedia, general_llm. Respond with ONLY the keyword."
    messages = [{"role": "system", "content": system}, {"role": "user", "content": state["user_message"]}]
    try:
        client = groq.Groq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None
        if not client:
            state["route"] = "general_llm"
            return {}
        completion = call_groq_with_retry(
            client.chat.completions.create,
            messages=messages,
            model="groq/llama3-8b-8192",  # lightweight model for routing only
            max_tokens=5,
        )
        route = completion.choices[0].message.content.strip().lower()
        allowed = {"rag", "calculator", "web_search", "wikipedia", "general_llm"}
        state["route"] = route if route in allowed else "general_llm"
    except Exception as e:
        # On any failure fall back to generic LLM route
        state.setdefault("errors", []).append(f"Router error: {e}")
        state["route"] = "general_llm"
    return {}


async def rag_node(state: Dict[str, Any]):
    """Execute the KnowledgeBaseTool (RAG)."""
    # The tool expects ``query`` plus ``db`` and ``user_id``
    result = await tool_registry.execute_tool(
        "search_knowledge_base",
        {"query": state["user_message"]},
        db=state.get("db"),
        user_id=state.get("user_id"),
    )
    # Store retrieved docs for later system prompt construction
    state["retrieved_docs"] = result
    # Append as a system message so the LLM sees the context
    _append_message(state, "system", f"Retrieved Knowledge Base Context:\n{result}")
    return {}


async def calculator_node(state: Dict[str, Any]):
    """Execute the CalculatorTool with the raw user message as the expression."""
    result = await tool_registry.execute_tool(
        "calculator",
        {"expression": state["user_message"]},
    )
    state["tool_results"].append(result)
    _append_message(state, "assistant", f"Calculator result: {result}")
    return {}


async def web_search_node(state: Dict[str, Any]):
    """Execute the WebSearchTool with the raw user message as the query."""
    result = await tool_registry.execute_tool(
        "web_search",
        {"query": state["user_message"]},
    )
    state["tool_results"].append(result)
    _append_message(state, "assistant", f"Web search result: {result}")
    return {}


async def wikipedia_node(state: Dict[str, Any]):
    """Execute the WikipediaTool with the raw user message as the query."""
    result = await tool_registry.execute_tool(
        "wikipedia_search",
        {"query": state["user_message"]},
    )
    state["tool_results"].append(result)
    _append_message(state, "assistant", f"Wikipedia result: {result}")
    return {}


async def process_tool_result_node(state: Dict[str, Any]):
    """After a tool runs, decide whether we need another tool.

    Simple heuristic: if the route was ``rag`` and we already have retrieved docs,
    we consider the tool step complete. For other routes we also finish.
    ``needs_more_tools`` can be toggled by future extensions.
    """
    # For now we always finish after a single tool call.
    state["needs_more_tools"] = False
    return {}


async def generate_response_node(state: Dict[str, Any]):
    """Final LLM call to generate the user‑facing answer.

    Uses the accumulated ``messages`` list (including any system/context messages).
    The response is stored in ``final_response`` and ``is_complete`` is set.
    """
    from app.core.config import settings
    from app.services.groq_retry import call_groq_with_retry
    import groq

    client = groq.Groq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None
    if not client:
        state["final_response"] = "GROQ_API_KEY not configured."
        state["is_complete"] = True
        return {}
    try:
        completion = call_groq_with_retry(
            client.chat.completions.create,
            messages=state["messages"],
            model="groq/compound-mini",
            max_tokens=2048,
        )
        answer = completion.choices[0].message.content
        state["final_response"] = answer
        state["is_complete"] = True
    except Exception as e:
        state.setdefault("errors", []).append(f"Final LLM error: {e}")
        state["final_response"] = f"Error generating response: {e}"
        state["is_complete"] = True
    return {}

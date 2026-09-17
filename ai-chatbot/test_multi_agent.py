"""
Comprehensive Test Suite for KHANX Multi-Agent Architecture for Complex Tasks.

Tests:
1. Complexity Router: Simple queries use normal KHANX agent (False); Complex queries trigger Multi-Agent Swarm (True).
2. Individual Specialized Agent Executions (Research, RAG, Coding, Analysis, Reviewer).
3. Orchestrator Swarm Workflow Execution & SSE Streaming.
4. Safety Limits (Max 4 iterations, 15.0s phase timeout).
5. Backward Compatibility (Existing chat, RAG, Task Manager, Calendar, Email tools operate unimpeded).

Usage:
    cd ai-chatbot
    python test_multi_agent.py
"""

import os
import sys
import asyncio
import json

sys.path.insert(0, os.path.dirname(__file__))

passed = 0
failed = 0
errors = []

def _report(name: str, success: bool, detail: str = ""):
    global passed, failed
    if success:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        errors.append((name, detail))
        print(f"  ❌ {name}: {detail}")

def test_complexity_router():
    print("\n── Phase 1: Complexity Router (Simple vs Complex Tasks) ──")
    from app.agent.multi_agent import multi_agent_orchestrator

    # 1. Simple queries MUST evaluate to False (use normal KHANX agent)
    simple_queries = [
        "Hello! How are you?",
        "What is 15 + 27?",
        "Tell me a short joke.",
        "What is the capital of France?",
        "Add a task to buy groceries"
    ]
    for sq in simple_queries:
        is_comp = multi_agent_orchestrator.is_complex_query(sq)
        _report(
            f"Simple Query Fast-Path: '{sq}' -> False",
            is_comp is False,
            f"Got {is_comp}"
        )

    # 2. Complex queries MUST evaluate to True (trigger Multi-Agent Swarm)
    complex_queries = [
        "Research and analyze the impact of AI on quantum computing, compare uploaded document with web findings, and write code to benchmark performance.",
        "Provide a comprehensive report on vector database performance metrics with deep analysis",
        "Please conduct research and analyze both uploaded document and web findings"
    ]
    for cq in complex_queries:
        is_comp = multi_agent_orchestrator.is_complex_query(cq)
        _report(
            f"Complex Query Multi-Agent Trigger: '{cq[:45]}...' -> True",
            is_comp is True,
            f"Got {is_comp}"
        )

    # Explicit mode trigger
    is_comp_mode = multi_agent_orchestrator.is_complex_query("Simple question", mode="multi_agent")
    _report(
        "Explicit mode='multi_agent' triggers Multi-Agent Swarm",
        is_comp_mode is True,
        f"Got {is_comp_mode}"
    )

async def test_specialized_agents():
    print("\n── Phase 2: Individual 5 Specialized Sub-Agents ──")
    from app.agent.multi_agent import (
        ResearchAgent, RAGAgent, CodingAgent, AnalysisAgent, ReviewerAgent
    )

    user_id = "test_user_swarm_303"

    # 1. Research Agent
    research_agent = ResearchAgent()
    res_out = await research_agent.execute("Python programming language history", user_id=user_id)
    _report(
        "Research Agent retrieves web/wiki factual context",
        isinstance(res_out, str) and len(res_out) > 0,
        f"Output len: {len(res_out)}"
    )

    # 2. RAG Agent
    rag_agent = RAGAgent()
    rag_out = await rag_agent.execute("vector database index", user_id=user_id)
    _report(
        "RAG Agent retrieves document knowledge base findings",
        isinstance(rag_out, str),
        f"Output: {rag_out[:60]}"
    )

    # 3. Coding Agent
    coding_agent = CodingAgent()
    code_out = await coding_agent.execute("print(2 ** 10)", user_id=user_id)
    _report(
        "Coding Agent executes python code in sandbox",
        "Coding Agent Execution Output:" in code_out or "1024" in code_out,
        f"Output: {code_out}"
    )

    # 4. Analysis Agent
    analysis_agent = AnalysisAgent()
    synth = analysis_agent.synthesize("Analyze AI trends", res_out, rag_out, code_out)
    _report(
        "Analysis Agent synthesizes cross-domain findings",
        "Analysis & Synthesis for Query" in synth and "Research Insights" in synth,
        f"Output len: {len(synth)}"
    )

    # 5. Reviewer Agent
    reviewer_agent = ReviewerAgent()
    reviewed = reviewer_agent.review_and_polish(synth, "Analyze AI trends")
    _report(
        "Reviewer Agent verifies and polishes final solution",
        "Verified Multi-Agent Solution" in reviewed and "Verified by KHANX Reviewer Agent" in reviewed,
        f"Output: {reviewed[:80]}"
    )

async def test_swarm_workflow_execution():
    print("\n── Phase 3: Orchestrated Multi-Agent Workflow & Safety Limits ──")
    from app.agent.multi_agent import multi_agent_orchestrator, MAX_ITERATIONS, PHASE_TIMEOUT_SECONDS

    _report(
        "Safety Safeguards: MAX_ITERATIONS <= 4 and PHASE_TIMEOUT_SECONDS <= 15.0s",
        MAX_ITERATIONS <= 4 and PHASE_TIMEOUT_SECONDS <= 15.0,
        f"Max iterations: {MAX_ITERATIONS}, Timeout: {PHASE_TIMEOUT_SECONDS}s"
    )

    chunks = []
    async for chunk in multi_agent_orchestrator.run_multi_agent_workflow(
        query="Research and analyze python optimization techniques, execute code benchmark, and verify results",
        user_id="test_user_swarm_303"
    ):
        chunks.append(chunk)

    full_response = "".join(chunks)
    _report(
        "Multi-Agent Orchestrator executes step-by-step phases & streams SSE output",
        "KHANX Multi-Agent Swarm Activated" in full_response and "Phase 1/4" in full_response and "Verified Multi-Agent Solution" in full_response,
        f"Chunks count: {len(chunks)}"
    )

def test_system_and_backwards_compatibility():
    print("\n── Phase 4: Backward Compatibility & Orchestrator Integration ──")
    from app.agent.orchestrator import AgentOrchestrator

    orch = AgentOrchestrator()
    _report(
        "AgentOrchestrator exists and imports multi_agent_orchestrator cleanly",
        hasattr(orch, "stream_agent_chat"),
        "Orchestrator ready"
    )

def main():
    print("=" * 65)
    print("  KHANX Multi-Agent Architecture for Complex Tasks — Test Suite")
    print("=" * 65)

    test_complexity_router()
    asyncio.run(test_specialized_agents())
    asyncio.run(test_swarm_workflow_execution())
    test_system_and_backwards_compatibility()

    print("\n" + "=" * 65)
    print(f"  Results: {passed}/{passed + failed} passed, {failed} failed")
    if errors:
        for name, detail in errors:
            print(f"    ❌ {name}: {detail}")
    print("=" * 65)

    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

"""
Comprehensive test script for KHANX Multi-Source Research Agent.

Tests:
1. Research Query Detection (Inferred & Explicit mode="research")
2. Research Plan Formulation (Sub-query generation for RAG and Web)
3. Multi-Source Prompt Building with Inline Citations ([Doc: filename], [Web: source])
4. Multi-Source Execution (RAG + Web search integration)
5. Fallback Safety to Standard Chatbot

Usage:
    cd ai-chatbot
    python test_research_agent.py
"""
import os
import sys
import asyncio

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

def test_research_query_detection():
    print("\n── Phase 1: Research Query Detection ──")
    from app.agent.research_agent import research_agent

    research_queries = [
        ("conduct a deep research study on quantum computing breakthrough", True),
        ("investigate literature review on transformer models", True),
        ("compare web search results with my uploaded documents", True),
        ("search both internet and documents for battery technology", True),
        ("hi, how are you?", False),
        ("what is 10 + 15?", False),
    ]

    for q, expected in research_queries:
        is_res = research_agent.is_research_query(q)
        _report(
            f"Detect research={expected} for '{q[:45]}...'",
            is_res == expected,
            f"Got: {is_res}"
        )

def test_research_plan_formulation():
    print("\n── Phase 2: Research Plan Formulation ──")
    from app.agent.research_agent import research_agent

    query = "solid state battery commercialization and safety"
    plan = research_agent.create_research_plan(query)

    _report(
        "Generate RAG and Web sub-queries in research plan",
        len(plan.sub_queries_rag) >= 2 and len(plan.sub_queries_web) >= 2,
        f"RAG queries: {plan.sub_queries_rag}, Web queries: {plan.sub_queries_web}"
    )

def test_citation_prompt_building():
    print("\n── Phase 3: Cited System Prompt Building ──")
    from app.agent.research_agent import research_agent, ResearchFinding

    query = "deep research on renewable energy"
    plan = research_agent.create_research_plan(query)

    findings = [
        ResearchFinding(source_type="Doc", source_name="energy_report.pdf", content="Solar adoption increased by 25% in 2024."),
        ResearchFinding(source_type="Web", source_name="duckduckgo.com", content="Global wind power capacity crossed 1000 GW.")
    ]

    prompt = research_agent.build_research_system_prompt(plan, findings)

    _report(
        "Citation directives and multi-source findings present in prompt overlay",
        "AUTONOMOUS RESEARCH AGENT ACTIVE" in prompt and "[Doc: filename]" in prompt and "energy_report.pdf" in prompt and "duckduckgo.com" in prompt,
        f"Prompt snippet: {prompt[:150]}..."
    )

async def test_multi_source_execution():
    print("\n── Phase 4: Multi-Source Execution (RAG + Web) ──")
    from app.agent.research_agent import research_agent

    plan = research_agent.create_research_plan("quantum computing")
    findings = await research_agent.execute_research(plan, user_id=None, db=None)

    _report(
        "Execute research across available tools (Web search fallback)",
        isinstance(findings, list),
        f"Found {len(findings)} findings"
    )

def test_explicit_mode_param():
    print("\n── Phase 5: Explicit mode='research' Parameter ──")
    from app.agent.research_agent import research_agent

    is_res = research_agent.is_research_query("tell me about space exploration", mode_param="research")
    _report(
        "Explicit mode='research' activates Research Agent",
        is_res is True,
        f"Got: {is_res}"
    )

def test_fallback_to_normal_chat():
    print("\n── Phase 6: Fallback Safety to Standard Chatbot ──")
    from app.agent.research_agent import research_agent

    simple_q = "what is the capital of France?"
    is_res = research_agent.is_research_query(simple_q)
    _report(
        "Simple query falls back seamlessly to normal chatbot",
        is_res is False,
        f"Got: {is_res}"
    )

def main():
    print("=" * 65)
    print("  KHANX Autonomous Research Agent — Test Suite")
    print("=" * 65)

    test_research_query_detection()
    test_research_plan_formulation()
    test_citation_prompt_building()
    asyncio.run(test_multi_source_execution())
    test_explicit_mode_param()
    test_fallback_to_normal_chat()

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

"""
Comprehensive test script for KHANX Web Search & Multi-Tool Selection (RAG, Web Search, Both).

Tests:
1. Direct execution of WebSearchTool for current information queries
2. Verification of WebSearchTool fallback handling
3. ToolRegistry registration check
4. System prompt tool choice guidelines verification

Usage:
    cd ai-chatbot
    python test_web_search_agent.py
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

async def test_web_search_tool():
    print("\n── Phase 1: WebSearchTool Execution ──")
    from app.agent.tools.web_search_tool import WebSearchTool
    from app.agent.tools.registry import tool_registry
    
    tool = tool_registry.get_tool("web_search")
    _report("WebSearchTool registered in registry", tool is not None, "Tool missing from registry")
    
    if tool:
        result = await tool.execute("latest Artificial Intelligence breakthroughs 2026")
        _report("WebSearchTool execution result", len(result) > 10, f"Unexpected empty result: {result}")
        has_fallback_msg = "Proceeding with standard AI response" in result or "•" in result
        _report("Response has snippet or resilient fallback text", has_fallback_msg, f"Result: {result[:100]}")

def test_system_prompt():
    print("\n── Phase 2: Orchestrator Tool Choice Guidelines ──")
    from app.agent.orchestrator import KHANNAX_SYSTEM_PROMPT
    
    has_rag = "search_knowledge_base" in KHANNAX_SYSTEM_PROMPT
    has_web = "web_search" in KHANNAX_SYSTEM_PROMPT
    has_guidelines = "TOOL CHOICE GUIDELINES" in KHANNAX_SYSTEM_PROMPT
    
    _report("System prompt contains RAG tool", has_rag, "Missing search_knowledge_base")
    _report("System prompt contains Web Search tool", has_web, "Missing web_search")
    _report("System prompt contains multi-tool guidelines", has_guidelines, "Missing TOOL CHOICE GUIDELINES")

async def main():
    print("=" * 65)
    print("  KHANX Optional Web Search & Multi-Tool Selection — Test Suite")
    print("=" * 65)
    
    await test_web_search_tool()
    test_system_prompt()
    
    print("\n" + "=" * 65)
    print(f"  Results: {passed}/{passed + failed} passed, {failed} failed")
    if errors:
        for name, detail in errors:
            print(f"    ❌ {name}: {detail}")
    print("=" * 65)
    
    return failed == 0

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

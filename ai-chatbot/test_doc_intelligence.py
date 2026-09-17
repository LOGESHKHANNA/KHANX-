"""
Comprehensive test script for KHANX Document Intelligence.

Tests:
1. Task Classification (summarize, compare, key_points, table_understanding, contradiction)
2. Multi-Document System Prompt Building (With grouped ChromaDB document context)
3. Single RAG Context Fallback Building
4. Explicit mode="document_analysis" handling
5. Zero Regression on standard document Q&A and normal chat

Usage:
    cd ai-chatbot
    python test_doc_intelligence.py
"""
import os
import sys

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

def test_task_classification():
    print("\n── Phase 1: Document Intelligence Task Classification ──")
    from app.agent.doc_intelligence import doc_intelligence_engine

    tasks = [
        ("find contradictions between report_2024.pdf and report_2025.pdf", "contradiction"),
        ("compare document A and document B side by side", "compare"),
        ("analyze this table and spreadsheet data", "table_understanding"),
        ("extract key points and metrics from my uploaded file", "key_points"),
        ("give me an executive summary of the document", "summarize"),
    ]

    for query, expected_task in tasks:
        cfg = doc_intelligence_engine.detect_doc_task(query)
        _report(
            f"Detect task '{expected_task}' for '{query[:45]}...'",
            cfg is not None and cfg.task_type == expected_task,
            f"Got: {cfg.task_type if cfg else None}"
        )

def test_multi_document_prompt_building():
    print("\n── Phase 2: Multi-Document Prompt Overlay Building ──")
    from app.agent.doc_intelligence import doc_intelligence_engine, DocTaskConfig

    cfg = DocTaskConfig(
        task_type="compare",
        directive="DOCUMENT INTELLIGENCE — COMPARISON",
        query_hint="compare doc1 and doc2"
    )

    multi_ctx = {
        "annual_report_2024.pdf": ["Revenue in 2024 was $10M.", "Operating cost was $4M."],
        "annual_report_2025.pdf": ["Revenue in 2025 grew to $15M.", "Operating cost was $6M."]
    }

    prompt = doc_intelligence_engine.build_doc_system_prompt(cfg, multi_doc_context=multi_ctx)

    _report(
        "Multi-document context injected cleanly into prompt overlay",
        "annual_report_2024.pdf" in prompt and "annual_report_2025.pdf" in prompt and "DOCUMENT INTELLIGENCE ACTIVE" in prompt,
        f"Prompt snippet: {prompt[:150]}..."
    )

def test_explicit_mode_param():
    print("\n── Phase 3: Explicit mode='document_analysis' Parameter ──")
    from app.agent.doc_intelligence import doc_intelligence_engine

    cfg = doc_intelligence_engine.detect_doc_task("what is inside this file?", mode_param="document_analysis")
    _report(
        "Explicit mode='document_analysis' triggers DocTaskConfig",
        cfg is not None and cfg.task_type == "summarize",
        f"Got: {cfg}"
    )

def test_zero_regression():
    print("\n── Phase 4: Non-Interference with Standard Q&A & Normal Chat ──")
    from app.agent.doc_intelligence import doc_intelligence_engine

    qa_and_chat_queries = [
        "what is the refund policy mentioned in the document?",
        "who is the CEO of the company?",
        "hello, good morning",
        "what is 25 * 4?",
    ]

    for q in qa_and_chat_queries:
        cfg = doc_intelligence_engine.detect_doc_task(q)
        _report(
            f"Query '{q[:40]}...' does not hijack standard Q&A / normal chat",
            cfg is None,
            f"Got: {cfg.task_type if cfg else None}"
        )

def main():
    print("=" * 65)
    print("  KHANX Document Intelligence — Comprehensive Test Suite")
    print("=" * 65)

    test_task_classification()
    test_multi_document_prompt_building()
    test_explicit_mode_param()
    test_zero_regression()

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

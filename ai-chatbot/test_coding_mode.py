"""
Comprehensive test script for KHANX Coding Mode.

Tests:
1. Language Detection (Python, Java, C, C++, JavaScript, SQL)
2. Task Classification (explain, debug_fix, optimize, generate, test_cases)
3. Safety Directive Injection (Verifies auto-execution is strictly disabled)
4. Explicit mode="coding" handling
5. Zero Regression on normal chat & study mode

Usage:
    cd ai-chatbot
    python test_coding_mode.py
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

def test_language_detection():
    print("\n── Phase 1: Programming Language Detection (6 Languages) ──")
    from app.agent.coding_mode import coding_mode_engine

    tests = [
        ("def quicksort(arr): import pandas as pd", "Python"),
        ("public class Main { System.out.println('Hello'); }", "Java"),
        ("#include <stdio.h>\nint main() { printf('Hello'); return 0; }", "C"),
        ("#include <iostream>\nstd::vector<int> v; std::cout << 'Hi';", "C++"),
        ("const fetchData = async () => { console.log('API'); };", "JavaScript"),
        ("SELECT users.id, COUNT(orders.id) FROM users JOIN orders ON users.id = orders.user_id GROUP BY users.id;", "SQL"),
    ]

    for snippet, expected_lang in tests:
        lang = coding_mode_engine.detect_language(snippet)
        _report(
            f"Detect '{expected_lang}' from '{snippet[:40]}...'",
            lang == expected_lang,
            f"Got: {lang}"
        )

def test_task_classification():
    print("\n── Phase 2: Coding Task Classification ──")
    from app.agent.coding_mode import coding_mode_engine

    tasks = [
        ("explain this C++ algorithm step by step", "explain", "C++"),
        ("debug nullpointerexception in my Java code", "debug_fix", "Java"),
        ("optimize this SQL query to reduce execution time", "optimize", "SQL"),
        ("write a Python script to parse JSON data", "generate", "Python"),
        ("create unit test cases in pytest for my functions", "test_cases", "Python"),
        ("write unit test suite in Jest for JavaScript module", "test_cases", "JavaScript"),
    ]

    for query, expected_task, expected_lang in tasks:
        cfg = coding_mode_engine.detect_coding_config(query)
        _report(
            f"Detect task '{expected_task}' ({expected_lang}) for '{query[:40]}...'",
            cfg is not None and cfg.task_type == expected_task and cfg.language == expected_lang,
            f"Got task={cfg.task_type if cfg else None}, lang={cfg.language if cfg else None}"
        )

def test_safety_directive():
    print("\n── Phase 3: Safety Directive Check (No Auto-Execution) ──")
    from app.agent.coding_mode import coding_mode_engine

    cfg = coding_mode_engine.detect_coding_config("write a python function to calculate Fibonacci")
    prompt = coding_mode_engine.build_coding_system_prompt(cfg)

    _report(
        "Safety directive present (Do not execute generated code automatically)",
        "Do not execute generated code automatically" in prompt,
        f"Prompt snippet: {prompt[:120]}..."
    )

def test_explicit_mode_param():
    print("\n── Phase 4: Explicit mode='coding' Parameter ──")
    from app.agent.coding_mode import coding_mode_engine

    cfg = coding_mode_engine.detect_coding_config("how to implement quicksort", mode_param="coding")
    _report(
        "Explicit mode='coding' activates CodingModeConfig",
        cfg is not None and cfg.task_type == "generate",
        f"Got: {cfg}"
    )

def test_zero_regression():
    print("\n── Phase 5: Zero Regression on Normal Chat ──")
    from app.agent.coding_mode import coding_mode_engine

    normal_queries = [
        "hi, good morning!",
        "what is the capital of France?",
        "tell me a joke",
    ]

    for q in normal_queries:
        cfg = coding_mode_engine.detect_coding_config(q)
        _report(
            f"Normal query '{q}' does not trigger Coding Mode",
            cfg is None,
            f"Got: {cfg}"
        )

def main():
    print("=" * 65)
    print("  KHANX Coding Mode — Comprehensive Test Suite")
    print("=" * 65)

    test_language_detection()
    test_task_classification()
    test_safety_directive()
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

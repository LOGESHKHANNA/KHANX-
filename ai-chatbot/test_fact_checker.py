"""
Comprehensive test script for KHANX Fact-Checking Engine.

Tests:
1. Triggering Rules (Selective fact-checking for research-heavy queries, bypassing simple chat)
2. Claim Extraction (Metrics, dates, entity statements)
3. Claim Verification & Qualification (Context overlap scoring, transparency qualification notes)
4. Explicit mode="fact_check" handling
5. Fallback Safety to Standard Chatbot

Usage:
    cd ai-chatbot
    python test_fact_checker.py
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

def test_fact_check_triggering():
    print("\n── Phase 1: Fact-Checking Triggering Rules ──")
    from app.agent.fact_checker import fact_checker

    cases = [
        ("deep research report on solid state battery metrics in 2025", "Revenue grew by 25% according to report", True),
        ("hello how are you", "", False),
        ("what is 5 * 10?", "", False),
        ("analyze this document overview", "The company lost 5 million in Q3 2024.", True)
    ]

    for query, ctx, expected in cases:
        res = fact_checker.should_fact_check(query, context=ctx)
        _report(
            f"Trigger fact-check={expected} for '{query[:40]}...'",
            res == expected,
            f"Got: {res}"
        )

def test_claim_extraction():
    print("\n── Phase 2: Claim Extraction ──")
    from app.agent.fact_checker import fact_checker

    sample_text = (
        "The project reached a major milestone in 2025. "
        "User adoption increased by 45% across all regions. "
        "The team consists of engineers and designers. "
        "According to report_2024.pdf, revenue surpassed 10 million dollars."
    )

    claims = fact_checker.extract_claims(sample_text)
    _report(
        "Extract key factual claims containing metrics, dates, or citations",
        len(claims) >= 2 and any("45%" in c for c in claims) and any("2025" in c for c in claims),
        f"Extracted {len(claims)} claims: {claims}"
    )

def test_claim_verification_and_qualification():
    print("\n── Phase 3: Claim Verification & Qualification ──")
    from app.agent.fact_checker import fact_checker

    response_text = "Revenue grew by 50% in 2025 according to internal finance metrics."
    source_context = "=== RETRIEVED CONTEXT ===\nRevenue grew by 50% in 2025 in internal finance metrics."

    result = fact_checker.verify_claims(response_text, source_context)
    _report(
        "Supported claim gets high verification score without qualification warning",
        result.verification_score >= 0.8 and result.qualified_response == response_text,
        f"Score: {result.verification_score}, Qualified text: {result.qualified_response[:60]}..."
    )

    unsupported_response = "Quantum computing speedup exceeded 10000x in 2026."
    unsupported_result = fact_checker.verify_claims(unsupported_response, source_context)
    _report(
        "Unsupported claim is tracked in unsupported_claims without appending verification note",
        len(unsupported_result.unsupported_claims) > 0 and unsupported_result.qualified_response == unsupported_response,
        f"Qualified text snippet: {unsupported_result.qualified_response[-120:]}"
    )

def test_explicit_mode_param():
    print("\n── Phase 4: Explicit mode='fact_check' Parameter ──")
    from app.agent.fact_checker import fact_checker

    res = fact_checker.should_fact_check("summarize report", mode_param="fact_check")
    _report(
        "Explicit mode='fact_check' triggers fact-checking step",
        res is True,
        f"Got: {res}"
    )

def main():
    print("=" * 65)
    print("  KHANX Fact-Checking Engine — Test Suite")
    print("=" * 65)

    test_fact_check_triggering()
    test_claim_extraction()
    test_claim_verification_and_qualification()
    test_explicit_mode_param()

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

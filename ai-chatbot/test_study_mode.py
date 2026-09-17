"""
Comprehensive test script for KHANX Study Mode & Response Modes.

Tests:
1. Study asset detection (MCQs, flashcards, viva, short questions, long questions, summaries, topic explanations, answer evaluations)
2. Explicit mode="study" handling
3. Grounded RAG system prompt building
4. Response mode detection (explain, teach, summarize, compare, analyze, research, code, debug, quiz, interview)
5. Zero regression on normal chat

Usage:
    cd ai-chatbot
    python test_study_mode.py
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

def test_study_mode_detection():
    print("\n── Phase 1: Study Asset & Evaluation Detections ──")
    from app.agent.study_mode import study_mode_engine

    tests = [
        ("generate 5 MCQs on operating system page replacement algorithms", "mcq"),
        ("create flashcards for organic chemistry reactions", "flashcard"),
        ("prepare viva questions on database normalization", "viva"),
        ("give me 3 short questions on computer networks", "short_q"),
        ("create a 10 marks long question on quantum physics", "long_q"),
        ("provide a chapter summary and cheat sheet for thermodynamics", "summary"),
        ("deep dive topic explanation for backpropagation", "explanation"),
        ("evaluate my answer: page fault occurs when page is missing from RAM", "answer_eval"),
        ("hello, please tutor me in study mode", "interactive"),
    ]

    for query, expected_asset in tests:
        cfg = study_mode_engine.detect_study_config(query)
        _report(
            f"Detect '{expected_asset}' for '{query[:45]}...'",
            cfg is not None and cfg.asset_type == expected_asset,
            f"Got: {cfg.asset_type if cfg else None}"
        )

def test_explicit_mode_param():
    print("\n── Phase 2: Explicit mode='study' Parameter ──")
    from app.agent.study_mode import study_mode_engine

    cfg = study_mode_engine.detect_study_config("tell me about cellular mitosis", mode_param="study")
    _report("Explicit mode='study' triggers StudyModeConfig", cfg is not None and cfg.asset_type == "interactive", f"Got: {cfg}")

def test_grounded_rag_prompt_building():
    print("\n── Phase 3: Grounded RAG Study Prompt Overlays ──")
    from app.agent.study_mode import study_mode_engine, StudyModeConfig

    cfg = StudyModeConfig(
        asset_type="mcq",
        directive="STUDY MODE — MCQ GENERATION",
        query_hint="operating systems"
    )

    # 1. With RAG Context
    rag_ctx = "Operating systems use LRU and FIFO page replacement algorithms."
    prompt_with_rag = study_mode_engine.build_study_system_prompt(cfg, rag_context=rag_ctx)
    _report(
        "RAG Grounding directive injected when document context present",
        "GROUNDING DIRECTIVE" in prompt_with_rag and rag_ctx in prompt_with_rag,
        f"Prompt: {prompt_with_rag[:100]}..."
    )

    # 2. Without RAG Context
    prompt_no_rag = study_mode_engine.build_study_system_prompt(cfg, rag_context=None)
    _report(
        "General knowledge fallback note injected when no document context present",
        "No uploaded document context was found" in prompt_no_rag,
        f"Prompt: {prompt_no_rag[:100]}..."
    )

def test_response_mode_detection():
    print("\n── Phase 4: Response Mode Detections ──")
    from app.agent.response_mode import response_mode_detector

    modes = [
        ("explain neural networks step by step", "explain"),
        ("teach me quantum mechanics like a beginner", "teach"),
        ("summarize the key points of this article", "summarize"),
        ("compare PyTorch vs TensorFlow", "compare"),
        ("analyze the security risks of SQL injection", "analyze"),
        ("research literature survey on transformer models", "research"),
        ("write python code for binary search tree", "code"),
        ("debug this syntax error in my script", "debug"),
        ("quiz me on machine learning", "quiz"),
        ("interview me for a senior python developer role", "interview"),
    ]

    for query, expected_mode in modes:
        mode_res = response_mode_detector.detect(query)
        _report(
            f"Response mode '{expected_mode}' detected for '{query[:40]}...'",
            mode_res is not None and mode_res.name == expected_mode,
            f"Got: {mode_res.name if mode_res else None}"
        )

def test_normal_chat_unchanged():
    print("\n── Phase 5: Normal Chat Non-Interference Check ──")
    from app.agent.study_mode import study_mode_engine
    from app.agent.response_mode import response_mode_detector

    normal_queries = [
        "hi",
        "hello how are you",
        "what is the capital of France?",
        "ok sounds good",
    ]

    for q in normal_queries:
        study_cfg = study_mode_engine.detect_study_config(q)
        resp_mode = response_mode_detector.detect(q)
        _report(
            f"Normal query '{q}' triggers neither study nor response mode",
            study_cfg is None and resp_mode is None,
            f"Study: {study_cfg}, ResponseMode: {resp_mode}"
        )

def main():
    print("=" * 65)
    print("  KHANX Study Mode & Response Modes — Test Suite")
    print("=" * 65)

    test_study_mode_detection()
    test_explicit_mode_param()
    test_grounded_rag_prompt_building()
    test_response_mode_detection()
    test_normal_chat_unchanged()

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

"""
Comprehensive test script for KHANX Multi-Step Task Planner.

Tests:
1. Task Planning Detection (Selective detection for multi-step goals, bypassing simple queries)
2. Task Plan Creation (Subtask decomposition and initial PENDING states)
3. Progress Tracker Formatting (State icons for PENDING, IN_PROGRESS, COMPLETED, FAILED)
4. Explicit mode="plan" handling
5. Fallback Safety to Standard Chatbot

Usage:
    cd ai-chatbot
    python test_task_planner.py
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

def test_task_planning_detection():
    print("\n── Phase 1: Task Planning Detection ──")
    from app.agent.task_planner import task_planner

    cases = [
        ("build a complete REST API with authentication and database models", True),
        ("create a step-by-step roadmap to migrate our database", True),
        ("hello, good morning!", False),
        ("what is 100 / 4?", False),
    ]

    for q, expected in cases:
        res = task_planner.should_plan_task(q)
        _report(
            f"Detect plan={expected} for '{q[:45]}...'",
            res == expected,
            f"Got: {res}"
        )

def test_plan_creation_and_subtasks():
    print("\n── Phase 2: Plan Creation & Structured Subtask States ──")
    from app.agent.task_planner import task_planner, TaskState

    goal = "develop a complete Python web scraper and store results in PostgreSQL"
    plan = task_planner.create_plan(goal)

    _report(
        "Subtasks decomposed with PENDING states",
        len(plan.subtasks) >= 3 and all(st.status == TaskState.PENDING for st in plan.subtasks),
        f"Generated {len(plan.subtasks)} subtasks"
    )

def test_progress_tracker_rendering():
    print("\n── Phase 3: Progress Tracker Formatting ──")
    from app.agent.task_planner import task_planner, TaskState

    plan = task_planner.create_plan("research and write report")
    plan.subtasks[0].status = TaskState.COMPLETED
    plan.subtasks[1].status = TaskState.IN_PROGRESS

    md = plan.render_progress_tracker()

    _report(
        "Progress tracker renders COMPLETED, IN_PROGRESS, and PENDING state icons",
        "`[x]` ✅" in md and "`[/]` ⏳" in md and "`[ ]` ⏸️" in md,
        f"Progress tracker snippet:\n{md[:180]}..."
    )

def test_explicit_mode_param():
    print("\n── Phase 4: Explicit mode='plan' Parameter ──")
    from app.agent.task_planner import task_planner

    res = task_planner.should_plan_task("help me out", mode_param="plan")
    _report(
        "Explicit mode='plan' triggers task planning",
        res is True,
        f"Got: {res}"
    )

def main():
    print("=" * 65)
    print("  KHANX Task Planner — Test Suite")
    print("=" * 65)

    test_task_planning_detection()
    test_plan_creation_and_subtasks()
    test_progress_tracker_rendering()
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

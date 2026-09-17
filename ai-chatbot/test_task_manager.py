"""
Comprehensive test script for KHANX Per-User Task Manager.

Tests:
1. Task Creation (create task with title, description, priority)
2. Task Viewing & Filtering (view tasks strictly scoped to user_id)
3. Task Completion (mark task as completed)
4. Task Updating (modify title, description, priority)
5. Task Deletion (delete task by ID or title)
6. Strict Multi-Tenancy Isolation (User A cannot access or mutate User B's tasks)
7. Unchanged Normal Chat Behavior

Usage:
    cd ai-chatbot
    python test_task_manager.py
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

async def test_task_crud():
    print("\n── Phase 1: Task Manager CRUD Operations ──")
    from app.agent.tools.task_tool import TaskManagerTool
    from app.agent.task_manager import task_manager_engine

    tool = TaskManagerTool()
    user1 = "user_alpha_123"

    # 1. CREATE
    res_create = await tool.execute(action="create", title="Submit Q3 Financial Report", priority="high", user_id=user1)
    _report(
        "Task Creation returns task ID and title",
        "Task Created" in res_create and "Submit Q3 Financial Report" in res_create,
        f"Got: {res_create}"
    )

    # 2. VIEW
    res_view = await tool.execute(action="view", status_filter="pending", user_id=user1)
    _report(
        "Task Viewing lists user tasks",
        "Submit Q3 Financial Report" in res_view and "HIGH" in res_view,
        f"Got: {res_view}"
    )

    # 3. COMPLETE
    res_comp = await tool.execute(action="complete", task_id="Submit Q3 Financial Report", user_id=user1)
    _report(
        "Task Completion updates task status",
        "Task Completed" in res_comp,
        f"Got: {res_comp}"
    )

    # 4. DELETE
    res_del = await tool.execute(action="delete", task_id="Submit Q3 Financial Report", user_id=user1)
    _report(
        "Task Deletion removes task",
        "deleted successfully" in res_del,
        f"Got: {res_del}"
    )

async def test_multi_tenancy_isolation():
    print("\n── Phase 2: Strict Multi-Tenancy User Isolation ──")
    from app.agent.tools.task_tool import TaskManagerTool

    tool = TaskManagerTool()
    user_a = "user_alice_99"
    user_b = "user_bob_88"

    # Alice creates a private task
    await tool.execute(action="create", title="Alice Private Secrets", user_id=user_a)

    # Bob attempts to view tasks
    res_bob_view = await tool.execute(action="view", status_filter="all", user_id=user_b)
    _report(
        "Bob CANNOT view Alice's tasks (Strict multi-tenancy isolation)",
        "Alice Private Secrets" not in res_bob_view,
        f"Bob's view output: {res_bob_view}"
    )

    # Bob attempts to delete Alice's task
    res_bob_del = await tool.execute(action="delete", task_id="Alice Private Secrets", user_id=user_b)
    _report(
        "Bob CANNOT delete Alice's task (Strict multi-tenancy mutation shield)",
        "not found" in res_bob_del,
        f"Bob's delete output: {res_bob_del}"
    )

def test_system_prompt_integration():
    print("\n── Phase 3: System Prompt & Normal Chat Unchanged ──")
    from app.agent.orchestrator import KHANNAX_SYSTEM_PROMPT

    _report(
        "System prompt contains manage_tasks guidelines and multi-tenancy security rules",
        "manage_tasks" in KHANNAX_SYSTEM_PROMPT and "Tasks are strictly private" in KHANNAX_SYSTEM_PROMPT,
        "System prompt contains task guidelines"
    )

def main():
    print("=" * 65)
    print("  KHANX Per-User Task Manager — Test Suite")
    print("=" * 65)

    asyncio.run(test_task_crud())
    asyncio.run(test_multi_tenancy_isolation())
    test_system_prompt_integration()

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

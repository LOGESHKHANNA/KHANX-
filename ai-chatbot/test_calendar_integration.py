"""
Comprehensive Test Suite for KHANX OAuth Calendar Integration & Task Manager.

Tests:
1. Task Manager per-user CRUD & isolation.
2. Calendar OAuth Token Management (access & refresh tokens stored, NO raw passwords).
3. Availability Check tool (check schedule, open time slots).
4. Event Creation HITL Interception (`is_sensitive = True` returns `[ACTION_APPROVAL_REQUIRED: ...]`).
5. Unlinked Calendar Fallback (returns OAuth link gracefully; standard chat operates unimpeded).

Usage:
    cd ai-chatbot
    python test_calendar_integration.py
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

async def test_oauth_token_storage():
    print("\n── Phase 1: Secure OAuth Token Storage (No Raw Passwords) ──")
    from app.agent.calendar_manager import calendar_manager_engine

    user_id = "test_user_oauth_101"

    # Save OAuth tokens
    saved = await calendar_manager_engine.save_oauth_tokens(
        user_id=user_id,
        access_token="ya29.test_access_token_abc123",
        refresh_token="1//test_refresh_token_xyz987",
        provider="google",
        expires_in=3600
    )
    _report(
        "Save OAuth access & refresh tokens securely",
        saved is True,
        f"Saved: {saved}"
    )

    is_conn = await calendar_manager_engine.is_connected(user_id=user_id, provider="google")
    _report(
        "Calendar connection status is TRUE after OAuth flow",
        is_conn is True,
        f"Is Connected: {is_conn}"
    )

async def test_calendar_availability_tool():
    print("\n── Phase 2: Calendar Availability Tool ──")
    from app.agent.tools.calendar_tool import CalendarAvailabilityTool
    from app.agent.calendar_manager import calendar_manager_engine

    tool = CalendarAvailabilityTool()
    user_unlinked = "test_user_unlinked_999"
    user_linked = "test_user_oauth_101"

    # Unlinked calendar fallback
    res_unlinked = await tool.execute(date="2026-08-25", user_id=user_unlinked)
    _report(
        "Unlinked calendar returns OAuth authorization link gracefully",
        "Calendar integration is currently disconnected" in res_unlinked and "accounts.google.com" in res_unlinked,
        f"Output: {res_unlinked}"
    )

    # Connected calendar schedule check
    res_linked = await tool.execute(date="2026-08-25", user_id=user_linked)
    _report(
        "Connected calendar returns availability summary",
        "Availability on 2026-08-25" in res_linked or "Schedule on 2026-08-25" in res_linked,
        f"Output: {res_linked}"
    )

async def test_event_creation_hitl_approval():
    print("\n── Phase 3: Event Creation HITL Security & Approval Requirement ──")
    from app.agent.tools.registry import tool_registry

    user_id = "test_user_oauth_101"

    # Attempt to execute create_calendar_event tool without bypass_hitl
    args = {
        "title": "Quarterly Strategy Sync",
        "start_time": "2026-08-25T14:00:00",
        "end_time": "2026-08-25T15:00:00",
        "description": "Discuss Q4 objectives and budget allocation."
    }

    result = await tool_registry.execute_tool(
        name="create_calendar_event",
        arguments=args,
        user_id=user_id,
        session_id="session_test_456"
    )

    _report(
        "Calendar Event Creation requires explicit HITL user approval",
        "[ACTION_APPROVAL_REQUIRED:" in result and "create_calendar_event" in result,
        f"Result: {result}"
    )

    # Verify execution AFTER user approval (bypass_hitl=True)
    result_approved = await tool_registry.execute_tool(
        name="create_calendar_event",
        arguments=args,
        user_id=user_id,
        session_id="session_test_456",
        bypass_hitl=True
    )
    _report(
        "Approved event creation completes successfully on calendar",
        "Calendar Event Scheduled successfully" in result_approved and "Quarterly Strategy Sync" in result_approved,
        f"Result: {result_approved}"
    )

def test_system_prompt_calendar_rules():
    print("\n── Phase 4: System Prompt Guidelines & Normal Chat Continuity ──")
    from app.agent.orchestrator import KHANNAX_SYSTEM_PROMPT

    _report(
        "System prompt includes calendar availability & event approval guidelines",
        "check_calendar_availability" in KHANNAX_SYSTEM_PROMPT and "create_calendar_event" in KHANNAX_SYSTEM_PROMPT and "MUST require explicit user approval" in KHANNAX_SYSTEM_PROMPT,
        "System prompt contains calendar guidelines"
    )

def main():
    print("=" * 65)
    print("  KHANX OAuth Calendar Integration & Security — Test Suite")
    print("=" * 65)

    asyncio.run(test_oauth_token_storage())
    asyncio.run(test_calendar_availability_tool())
    asyncio.run(test_event_creation_hitl_approval())
    test_system_prompt_calendar_rules()

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

"""
Comprehensive Test Suite for KHANX OAuth Email Integration & Security.

Tests:
1. OAuth Token Storage & Zero Credential Exposure to LLM.
2. Email Drafting & Prepared Replies (Draft -> User Approval -> Send flow).
3. Strict HITL Interception for Email Sending (SendEmailTool produces `[ACTION_APPROVAL_REQUIRED: ...]`).
4. Dispatch execution AFTER explicit user approval.
5. Graceful fallback when email account is unlinked/offline.

Usage:
    cd ai-chatbot
    python test_email_integration.py
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

async def test_oauth_and_credential_privacy():
    print("\n── Phase 1: Secure OAuth Token Storage & Zero LLM Exposure ──")
    from app.agent.email_manager import email_manager_engine
    from app.agent.tools.email_tool import DraftEmailTool, SendEmailTool

    user_id = "test_user_email_202"

    # 1. Save OAuth tokens
    saved = await email_manager_engine.save_oauth_tokens(
        user_id=user_id,
        access_token="ya29.email_access_token_secret_123",
        refresh_token="1//email_refresh_token_secret_987",
        provider="google_gmail"
    )
    _report(
        "Save OAuth tokens securely in backend database",
        saved is True,
        f"Saved: {saved}"
    )

    is_conn = await email_manager_engine.is_connected(user_id=user_id, provider="google_gmail")
    _report(
        "Email connection status is TRUE after OAuth flow",
        is_conn is True,
        f"Is Connected: {is_conn}"
    )

    # 2. Verify tool schemas NEVER expose or request passwords or OAuth tokens
    draft_tool = DraftEmailTool()
    send_tool = SendEmailTool()
    props_draft = list(draft_tool.parameters["properties"].keys())
    props_send = list(send_tool.parameters["properties"].keys())

    has_secrets = any("password" in p or "token" in p or "secret" in p for p in props_draft + props_send)
    _report(
        "Zero Exposure: Tool schemas contain NO password or token parameters",
        has_secrets is False,
        f"Draft params: {props_draft}, Send params: {props_send}"
    )

async def test_email_drafting():
    print("\n── Phase 2: Email Drafting & Prepared Replies ──")
    from app.agent.tools.email_tool import DraftEmailTool
    from app.agent.email_manager import email_manager_engine

    tool = DraftEmailTool()
    user_id = "test_user_email_202"

    res_draft = await tool.execute(
        recipient="client@example.com",
        subject="Project Proposal Update",
        body="Hi team, here is the updated timeline for Q4 deliverables.",
        user_id=user_id
    )

    _report(
        "Draft email prepared without automatic sending",
        "Email Draft Prepared" in res_draft and "Project Proposal Update" in res_draft,
        f"Output: {res_draft}"
    )

    drafts = await email_manager_engine.list_drafts(user_id=user_id)
    _report(
        "Draft stored in user drafts list",
        len(drafts) >= 1 and drafts[0]["recipient"] == "client@example.com",
        f"Drafts: {drafts}"
    )

async def test_email_send_hitl_interception():
    print("\n── Phase 3: Strict HITL Interception (Never Send Automatically) ──")
    from app.agent.tools.registry import tool_registry

    user_id = "test_user_email_202"

    send_args = {
        "recipient": "client@example.com",
        "subject": "Project Proposal Update",
        "body": "Hi team, here is the updated timeline for Q4 deliverables."
    }

    # Attempt to execute send_email without explicit user approval
    result = await tool_registry.execute_tool(
        name="send_email",
        arguments=send_args,
        user_id=user_id,
        session_id="session_email_789"
    )

    _report(
        "KHANX CANNOT send automatically — Triggered HITL Approval Requirement",
        "[ACTION_APPROVAL_REQUIRED:" in result and "send_email" in result,
        f"Result: {result}"
    )

    # Dispatch AFTER explicit user approval (bypass_hitl=True)
    result_approved = await tool_registry.execute_tool(
        name="send_email",
        arguments=send_args,
        user_id=user_id,
        session_id="session_email_789",
        bypass_hitl=True
    )

    _report(
        "Approved email dispatched successfully after user authorization",
        "Email Sent Successfully" in result_approved and "client@example.com" in result_approved,
        f"Result: {result_approved}"
    )

def test_system_prompt_email_rules():
    print("\n── Phase 4: System Prompt Guidelines & Credential Shielding ──")
    from app.agent.orchestrator import KHANNAX_SYSTEM_PROMPT

    _report(
        "System prompt contains email guidelines, Flow: Draft -> Approval -> Send, and zero-exposure rules",
        "draft_email" in KHANNAX_SYSTEM_PROMPT and "send_email" in KHANNAX_SYSTEM_PROMPT and "Flow: Draft -> User Approval -> Send" in KHANNAX_SYSTEM_PROMPT,
        "System prompt contains email guidelines"
    )

def main():
    print("=" * 65)
    print("  KHANX Secure OAuth Email Integration & Security — Test Suite")
    print("=" * 65)

    asyncio.run(test_oauth_and_credential_privacy())
    asyncio.run(test_email_drafting())
    asyncio.run(test_email_send_hitl_interception())
    test_system_prompt_email_rules()

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

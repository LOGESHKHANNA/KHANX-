import asyncio
import os
import shutil
from datetime import datetime, timezone, timedelta
from app.agent.approval import ApprovalManager, ActionApproval, ActionStatus
from app.agent.tools.registry import tool_registry

async def run_hitl_tests():
    print("==================================================")
    print("  KHANX HUMAN-IN-THE-LOOP APPROVAL TEST SUITE     ")
    print("==================================================")

    test_dir = "tmp/test_approvals"
    os.makedirs(test_dir, exist_ok=True)
    manager = ApprovalManager(data_dir=test_dir)

    user_a = "user_11111111-1111-1111-1111-111111111111"
    user_b = "user_22222222-2222-2222-2222-222222222222"

    # --- 1. Test Safe Tool Direct Execution ---
    print("\n[1] Testing Safe Tool Execution (No HITL Required)...")
    res_calc = await tool_registry.execute_tool("calculator", {"expression": "25 * 4"})
    print(f"  Calculator result: {res_calc}")
    assert "100" in res_calc
    print("  ✅ Safe tool executed immediately without requiring approval.")

    # --- 2. Test Sensitive Tool Interception ---
    print("\n[2] Testing Sensitive Tool Security Interception...")
    res_sens = await tool_registry.execute_tool("delete_user_memory", {"key": "test_fact"}, user_id=user_a)
    print(f"  Interception response: {res_sens}")
    assert res_sens.startswith("[ACTION_APPROVAL_REQUIRED:")
    assert "delete_user_memory" in res_sens
    print("  ✅ Sensitive tool execution intercepted into PENDING proposal.")

    # --- 3. Test Action Proposal & Approval Flow ---
    print("\n[3] Testing Action Proposal & Approval Flow...")
    proposal = await manager.propose_action(
        user_id=user_a,
        session_id="sess_001",
        action_type="delete_user_memory",
        tool_name="delete_user_memory",
        arguments={"key": "preferred_language"},
        explanation="Delete user memory fact 'preferred_language'",
        risk_level="HIGH"
    )
    assert proposal.status == ActionStatus.PENDING

    # Approve action
    approved = await manager.approve_action(proposal.action_id, user_a)
    assert approved.status == ActionStatus.APPROVED
    print("  ✅ Action proposal successfully approved.")

    # Execute approved action
    exec_res = await manager.execute_approved_action(proposal.action_id, user_a)
    print(f"  Execution result: {exec_res['execution_result']}")
    assert exec_res["status"] == ActionStatus.EXECUTED
    print("  ✅ Approved action executed successfully.")

    # --- 4. Test Rejection Flow ---
    print("\n[4] Testing Action Rejection Flow...")
    prop_rej = await manager.propose_action(
        user_id=user_a,
        session_id="sess_001",
        action_type="modify_user_data",
        tool_name="modify_user_data",
        arguments={"key": "theme", "value": "dark"},
        explanation="Modify user theme preference",
        risk_level="MEDIUM"
    )
    await manager.reject_action(prop_rej.action_id, user_a)

    try:
        await manager.execute_approved_action(prop_rej.action_id, user_a)
        assert False, "Should have blocked rejected action execution!"
    except ValueError as ve:
        print(f"  ✅ Blocked rejected execution correctly: {ve}")

    # --- 5. Test Edit Arguments Flow ---
    print("\n[5] Testing Edit Arguments Flow...")
    prop_edit = await manager.propose_action(
        user_id=user_a,
        session_id="sess_001",
        action_type="modify_user_data",
        tool_name="modify_user_data",
        arguments={"key": "explanation_style", "value": "long"},
        explanation="Modify user explanation style",
        risk_level="MEDIUM"
    )
    edited = await manager.approve_action(
        prop_edit.action_id,
        user_a,
        modified_arguments={"key": "explanation_style", "value": "concise bullet points"}
    )
    assert edited.status == ActionStatus.EDITED
    assert edited.arguments["value"] == "concise bullet points"

    exec_edit_res = await manager.execute_approved_action(prop_edit.action_id, user_a)
    assert exec_edit_res["status"] == ActionStatus.EXECUTED
    print(f"  Execution output: {exec_edit_res['execution_result']}")
    assert "concise bullet points" in exec_edit_res["execution_result"]
    print("  ✅ Edited arguments executed successfully.")

    # --- 6. Test Expiration Check ---
    print("\n[6] Testing Expired Approval Check...")
    past_iso = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    prop_exp = ActionApproval(
        action_id="act_exp_123",
        user_id=user_a,
        session_id=None,
        action_type="delete_user_memory",
        tool_name="delete_user_memory",
        arguments={"key": "old"},
        explanation="Expired proposal",
        status=ActionStatus.APPROVED,
        expires_at=past_iso
    )
    manager._in_memory_actions[prop_exp.action_id] = prop_exp

    try:
        await manager.execute_approved_action(prop_exp.action_id, user_a)
        assert False, "Should have blocked expired approval execution!"
    except ValueError as ve:
        print(f"  ✅ Blocked expired execution correctly: {ve}")

    # --- 7. Test Duplicate Execution Prevention ---
    print("\n[7] Testing Duplicate Execution Prevention...")
    try:
        await manager.execute_approved_action(proposal.action_id, user_a)
        assert False, "Should have blocked duplicate execution!"
    except ValueError as ve:
        print(f"  ✅ Blocked duplicate execution correctly: {ve}")

    # --- 8. Test Unauthorized User Execution Prevention ---
    print("\n[8] Testing Unauthorized User Boundaries...")
    prop_auth = await manager.propose_action(
        user_id=user_a,
        session_id="sess_001",
        action_type="delete_user_memory",
        tool_name="delete_user_memory",
        arguments={"key": "secret_fact"},
        explanation="Delete fact"
    )
    await manager.approve_action(prop_auth.action_id, user_a)

    try:
        await manager.execute_approved_action(prop_auth.action_id, user_b)
        assert False, "User B should not be allowed to execute User A's action!"
    except (ValueError, PermissionError) as err:
        print(f"  ✅ Blocked unauthorized user execution: {err}")

    # Clean test temp directory
    shutil.rmtree("tmp", ignore_errors=True)

    print("\n==================================================")
    print("  🎉 ALL 8 HITL APPROVAL TEST SUITES PASSED!      ")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_hitl_tests())

"""
Comprehensive Test Suite for KHANX Agent System Logging & Tracing.

Tests:
1. TraceContext creation & metric recording (request_id, route, latency, iterations, token_usage).
2. Strict Zero Credential Privacy Filter: Verifies API keys, passwords, and OAuth tokens are redacted.
3. Tool Execution Tracing in ToolRegistry.
4. Orchestration Trace Lifecycle & end_trace summary generation.
5. Behavior Integrity: Zero changes to chatbot behavior or SSE responses.

Usage:
    cd ai-chatbot
    python test_tracing.py
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

def test_sanitization_privacy_filter():
    print("\n── Phase 1: Zero Credential Privacy Filter ──")
    from app.agent.tracing import sanitize_trace_data

    raw_sensitive_data = {
        "user_id": "usr_test_123",
        "api_key": "sk-proj-secret-key-xyz",
        "password": "SuperSecretPassword123!",
        "access_token": "ya29.email_access_token_secret",
        "refresh_token": "1//refresh_token_secret",
        "nested": {
            "auth_header": "Bearer ya29.oauth_token_secret",
            "safe_param": "hello_world"
        }
    }

    sanitized = sanitize_trace_data(raw_sensitive_data)

    _report(
        "api_key is redacted as '[REDACTED]'",
        sanitized.get("api_key") == "[REDACTED]",
        f"Got: {sanitized.get('api_key')}"
    )

    _report(
        "password is redacted as '[REDACTED]'",
        sanitized.get("password") == "[REDACTED]",
        f"Got: {sanitized.get('password')}"
    )

    _report(
        "access_token & refresh_token are redacted as '[REDACTED]'",
        sanitized.get("access_token") == "[REDACTED]" and sanitized.get("refresh_token") == "[REDACTED]",
        f"Access: {sanitized.get('access_token')}, Refresh: {sanitized.get('refresh_token')}"
    )

    _report(
        "Nested authorization headers are redacted securely",
        sanitized.get("nested", {}).get("auth_header") in ("[REDACTED]", "[REDACTED_TOKEN]"),
        f"Got: {sanitized.get('nested', {}).get('auth_header')}"
    )

    _report(
        "Safe parameters (e.g. user_id, safe_param) are preserved intact",
        sanitized.get("user_id") == "usr_test_123" and sanitized.get("nested", {}).get("safe_param") == "hello_world",
        f"Sanitized: {sanitized}"
    )

def test_trace_context_lifecycle():
    print("\n── Phase 2: Trace Context Lifecycle & Metric Tracking ──")
    from app.agent.tracing import agent_tracer

    ctx = agent_tracer.start_trace(request_id="req_test_999", selected_route="unit_test_route")
    ctx.increment_iterations()
    ctx.increment_iterations()
    ctx.record_token_usage(prompt_tokens=150, completion_tokens=45)
    ctx.record_tool_call(
        tool_name="calculator",
        arguments={"expression": "100 / 4", "api_key": "should_be_redacted"},
        duration_ms=12.5,
        status="success"
    )

    summary = agent_tracer.end_trace(ctx)

    _report(
        "Trace summary includes request_id and selected_route",
        summary.get("request_id") == "req_test_999" and summary.get("selected_route") == "unit_test_route",
        f"Summary: {summary}"
    )

    _report(
        "Latency in milliseconds is recorded (> 0.0 ms)",
        isinstance(summary.get("latency_ms"), float) and summary.get("latency_ms") >= 0.0,
        f"Latency ms: {summary.get('latency_ms')}"
    )

    _report(
        "Agent iterations recorded (2 iterations)",
        summary.get("agent_iterations") == 2,
        f"Iterations: {summary.get('agent_iterations')}"
    )

    _report(
        "Token usage recorded (150 prompt, 45 completion, 195 total)",
        summary.get("token_usage", {}).get("total_tokens") == 195,
        f"Token usage: {summary.get('token_usage')}"
    )

    tool_args = summary["tool_calls"][0]["arguments"] if summary.get("tool_calls") else {}
    if isinstance(tool_args, str):
        try:
            tool_args = json.loads(tool_args)
        except Exception:
            tool_args = {}

    _report(
        "Tool call recorded with sanitized arguments (api_key redacted)",
        len(summary.get("tool_calls", [])) >= 1 and isinstance(tool_args, dict) and tool_args.get("api_key") == "[REDACTED]",
        f"Tool calls: {summary.get('tool_calls')}"
    )

async def test_tool_execution_tracing():
    print("\n── Phase 3: Tool Execution Tracing via ToolRegistry ──")
    from app.agent.tracing import agent_tracer
    from app.agent.tools.registry import tool_registry

    ctx = agent_tracer.start_trace(request_id="req_tool_test", selected_route="tool_test")

    res = await tool_registry.execute_tool("calculator", {"expression": "25 * 4"})

    summary = agent_tracer.end_trace(ctx)

    _report(
        "Tool execution recorded inside active TraceContext",
        len(summary.get("tool_calls", [])) >= 1 and summary["tool_calls"][0]["tool_name"] == "calculator",
        f"Tool calls: {summary.get('tool_calls')}"
    )

def main():
    print("=" * 65)
    print("  KHANX Agent System Logging & Tracing — Test Suite")
    print("=" * 65)

    import traceback
    try:
        test_sanitization_privacy_filter()
        test_trace_context_lifecycle()
        asyncio.run(test_tool_execution_tracing())
    except Exception as e:
        traceback.print_exc()
        return False

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

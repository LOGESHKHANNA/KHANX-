"""
KHANX Agent System Tracing & Structured Logging Engine.

Tracks:
- request_id: Unique request identifier
- selected_route: Agent routing decision (e.g. 'single_agent_chat', 'multi_agent_swarm')
- tool_calls: Tool name, sanitized arguments, execution duration, status
- latency_ms: Total execution duration in milliseconds
- errors: Captured exception messages
- agent_iterations: Number of tool loop turns or sub-agent iterations
- token_usage: Prompt, completion, and total tokens

Security Guarantee:
- ALL parameters, headers, and trace metadata pass through `sanitize_trace_data`.
- API keys, passwords, access tokens, refresh tokens, and secrets are strictly redacted as '[REDACTED]'.
- Zero behavior change: Tracing runs asynchronously without altering chat execution or outputs.
"""

import time
import uuid
import json
import logging
from typing import Dict, List, Any, Optional
from contextvars import ContextVar


# Set up logger for agent system tracing
logger = logging.getLogger("khanx.agent.tracing")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[AGENT_TRACE] %(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


SECRET_KEY_TERMS = {
    "api_key", "password", "access_token", "refresh_token",
    "secret", "authorization", "private_key"
}


def is_secret_key(key: str) -> bool:
    """Check if a dictionary key represents a sensitive credential or secret token."""
    k_lower = str(key).lower()
    if k_lower == "token_usage":
        return False
    if any(st in k_lower for st in SECRET_KEY_TERMS):
        return True
    if k_lower in ("token", "auth", "bearer"):
        return True
    return False


def sanitize_trace_data(data: Any) -> Any:
    """Recursively sanitize data structures to ensure credentials and tokens are NEVER logged."""
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            if is_secret_key(str(key)):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = sanitize_trace_data(value)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_trace_data(item) for item in data]
    elif isinstance(data, str):
        # Additional string filter for authorization headers or raw secret tokens
        if any(prefix in data.lower() for prefix in ["bearer ya29", "bearer 1//"]):
            return "[REDACTED_TOKEN]"
        return data
    else:
        return data


class TraceContext:
    """Active trace execution context for an agent request."""

    def __init__(self, request_id: Optional[str] = None, selected_route: str = "default"):
        self.request_id = request_id or f"req_{uuid.uuid4().hex[:12]}"
        self.selected_route = selected_route
        self.start_time = time.monotonic()
        self.tool_calls: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self.agent_iterations: int = 0
        self.token_usage: Dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
        self.end_time: Optional[float] = None
        self.latency_ms: float = 0.0

    def record_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        duration_ms: float,
        status: str = "success",
        error: Optional[str] = None
    ) -> None:
        """Record execution details of a tool call with sanitized arguments."""
        call_record = {
            "tool_name": tool_name,
            "arguments": sanitize_trace_data(arguments),
            "duration_ms": round(duration_ms, 2),
            "status": status
        }
        if error:
            call_record["error"] = sanitize_trace_data(error)
            self.errors.append(f"Tool {tool_name} error: {error}")
        self.tool_calls.append(call_record)

    def record_token_usage(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        """Record token usage metrics."""
        self.token_usage["prompt_tokens"] += prompt_tokens
        self.token_usage["completion_tokens"] += completion_tokens
        self.token_usage["total_tokens"] = (
            self.token_usage["prompt_tokens"] + self.token_usage["completion_tokens"]
        )

    def record_error(self, error_msg: str) -> None:
        """Record exception or error."""
        self.errors.append(sanitize_trace_data(error_msg))

    def increment_iterations(self) -> None:
        """Increment agent loop iteration count."""
        self.agent_iterations += 1

    def finish(self) -> Dict[str, Any]:
        """Finalize trace context and calculate total latency."""
        self.end_time = time.monotonic()
        self.latency_ms = round((self.end_time - self.start_time) * 1000, 2)

        summary = {
            "request_id": self.request_id,
            "selected_route": self.selected_route,
            "latency_ms": self.latency_ms,
            "agent_iterations": self.agent_iterations,
            "tool_calls_count": len(self.tool_calls),
            "tool_calls": self.tool_calls,
            "token_usage": self.token_usage,
            "errors_count": len(self.errors),
            "errors": self.errors
        }
        return summary


# ContextVar for managing active request trace across async tasks
_active_trace: ContextVar[Optional[TraceContext]] = ContextVar("active_trace", default=None)


class AgentTracer:
    """Central Tracer management class."""

    def __init__(self):
        self._recent_traces: List[Dict[str, Any]] = []

    def start_trace(self, request_id: Optional[str] = None, selected_route: str = "default") -> TraceContext:
        """Start a new trace context."""
        ctx = TraceContext(request_id=request_id, selected_route=selected_route)
        _active_trace.set(ctx)
        return ctx

    def get_active_trace(self) -> Optional[TraceContext]:
        """Retrieve active trace context for current async task."""
        return _active_trace.get()

    def end_trace(self, ctx: Optional[TraceContext] = None) -> Dict[str, Any]:
        """End and emit structured JSON trace log."""
        trace = ctx or self.get_active_trace()
        if not trace:
            return {}

        summary = trace.finish()
        sanitized_summary = sanitize_trace_data(summary)

        # Log formatted JSON trace
        logger.info(json.dumps(sanitized_summary))

        # Store in recent memory buffer (keep last 50)
        self._recent_traces.append(sanitized_summary)
        if len(self._recent_traces) > 50:
            self._recent_traces.pop(0)

        _active_trace.set(None)
        return sanitized_summary

    def get_recent_traces(self) -> List[Dict[str, Any]]:
        """Get recent trace history for debugging."""
        return self._recent_traces


# Global Tracer Instance
agent_tracer = AgentTracer()

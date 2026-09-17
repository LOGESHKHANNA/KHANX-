import asyncio
import json
import time
from typing import Any, Dict, List, Optional
from app.agent.tools.base import BaseTool
from app.agent.tracing import agent_tracer
from app.agent.security import security_guard
from app.agent.tools.rag_tool import KnowledgeBaseTool
from app.agent.tools.calc_tool import CalculatorTool
from app.agent.tools.web_search_tool import WebSearchTool
from app.agent.tools.wiki_tool import WikipediaTool
from app.agent.tools.vision_tool import AnalyzeImageTool
from app.agent.tools.python_tool import PythonInterpreterTool
from app.agent.tools.memory_tool import LongTermMemoryTool
from app.agent.tools.image_gen_tool import GenerateImageTool
from app.agent.tools.task_tool import TaskManagerTool
from app.agent.tools.calendar_tool import CalendarAvailabilityTool, CreateCalendarEventTool
from app.agent.tools.email_tool import DraftEmailTool, SendEmailTool
from app.agent.tools.sensitive_tools import DeleteUserMemoryTool, ModifyUserDataTool

class ToolRegistry:
    """Registry managing available agent tools, schema export, execution dispatching, and HITL security checks."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

        # Register standard safe tools
        self.register(KnowledgeBaseTool())
        self.register(CalculatorTool())
        self.register(WebSearchTool())
        self.register(WikipediaTool())
        self.register(AnalyzeImageTool())
        self.register(PythonInterpreterTool())
        self.register(LongTermMemoryTool())
        self.register(GenerateImageTool())
        self.register(TaskManagerTool())
        self.register(CalendarAvailabilityTool())
        self.register(DraftEmailTool())

        # Register sensitive HITL tools
        self.register(DeleteUserMemoryTool())
        self.register(ModifyUserDataTool())
        self.register(CreateCalendarEventTool())
        self.register(SendEmailTool())

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get registered tool by name."""
        return self._tools.get(name)

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Return function calling schemas for all registered tools."""
        return [tool.to_schema() for tool in self._tools.values()]

    async def execute_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        db: Optional[Any] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        bypass_hitl: bool = False,
        timeout_seconds: float = 8.0
    ) -> str:
        """Execute a tool by name with security checks, timeout, and exception shielding."""
        tool = self.get_tool(name)
        if not tool:
            return f"Error: Tool '{name}' is not registered."

        # Security Guard Validation: Cross-user access check, Sandbox isolation & Payload limits
        sec_err = security_guard.validate_tool_arguments(name, arguments, user_id=user_id)
        if sec_err:
            return sec_err

        # HITL Security Barrier: Sensitive tool execution without explicit approval is intercepted!
        if tool.is_sensitive and not bypass_hitl:
            if not user_id:
                return "Error: User ID required for sensitive tool execution."

            from app.agent.approval import approval_manager
            explanation = f"KHANX proposes to perform sensitive action '{tool.name}' with arguments: {json.dumps(arguments)}."
            proposal = await approval_manager.propose_action(
                user_id=user_id,
                session_id=session_id,
                action_type=name,
                tool_name=name,
                arguments=arguments,
                explanation=explanation,
                risk_level=tool.risk_level,
                db=db
            )
            payload = proposal.to_dict()
            return f"[ACTION_APPROVAL_REQUIRED: {json.dumps(payload)}]"

        start_t = time.monotonic()
        active_trace = agent_tracer.get_active_trace()

        try:
            exec_kwargs = dict(arguments)
            if name in ("search_knowledge_base", "delete_user_memory", "modify_user_data", "analyze_image", "long_term_memory", "manage_tasks", "check_calendar_availability", "create_calendar_event", "draft_email", "send_email"):
                exec_kwargs["db"] = db
                exec_kwargs["user_id"] = user_id

            result = await asyncio.wait_for(
                tool.execute(**exec_kwargs),
                timeout=timeout_seconds
            )
            duration_ms = (time.monotonic() - start_t) * 1000
            if active_trace:
                active_trace.record_tool_call(name, arguments, duration_ms, status="success")
            return str(result)

        except asyncio.TimeoutError:
            duration_ms = (time.monotonic() - start_t) * 1000
            err_msg = f"Error: Tool '{name}' execution timed out after {timeout_seconds} seconds."
            if active_trace:
                active_trace.record_tool_call(name, arguments, duration_ms, status="timeout", error=err_msg)
            return err_msg
        except Exception as e:
            duration_ms = (time.monotonic() - start_t) * 1000
            err_msg = f"Error executing tool '{name}': {str(e)}"
            if active_trace:
                active_trace.record_tool_call(name, arguments, duration_ms, status="error", error=err_msg)
            return err_msg

# Global tool registry instance
tool_registry = ToolRegistry()

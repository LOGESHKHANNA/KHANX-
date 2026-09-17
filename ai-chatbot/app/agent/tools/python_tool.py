"""
Python Interpreter Tool for KHANX agent framework.
Executes Python code in an isolated subprocess sandbox for data analysis and calculations.
"""
from typing import Any, Dict
from app.agent.tools.base import BaseTool
from app.agent.sandbox import execute_python_code_sandboxed

class PythonInterpreterTool(BaseTool):
    """Tool allowing KHANX to execute Python code in an isolated sandbox for data analysis."""

    name = "python_interpreter"
    description = (
        "Execute Python code safely in an isolated sandbox for data analysis, "
        "CSV processing, statistical calculations, and data transformations. Use print() to display output."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code snippet to execute inside the isolated sandbox."
            }
        },
        "required": ["code"]
    }
    is_sensitive = False
    risk_level = "LOW"

    async def execute(self, code: str, **kwargs: Any) -> str:
        """Execute Python snippet inside restricted subprocess sandbox."""
        return execute_python_code_sandboxed(code=code, timeout_seconds=5.0)

import ast
import math
import re
from typing import Any, Dict
from app.agent.tools.base import BaseTool

# Approved math functions & constants
ALLOWED_NAMES = {
    'abs': abs,
    'round': round,
    'min': min,
    'max': max,
    'sum': sum,
    'pow': pow,
    'sqrt': math.sqrt,
    'sin': math.sin,
    'cos': math.cos,
    'tan': math.tan,
    'log': math.log,
    'exp': math.exp,
    'pi': math.pi,
    'e': math.e,
}

class SafeEvaluator(ast.NodeVisitor):
    """Safely evaluates an AST expression without arbitrary code execution risks."""

    def visit_Expression(self, node: ast.Expression):
        return self.visit(node.body)

    def visit_Num(self, node: ast.Num):  # Python < 3.8
        return node.n

    def visit_Constant(self, node: ast.Constant):  # Python >= 3.8
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")

    def visit_Name(self, node: ast.Name):
        if node.id in ALLOWED_NAMES:
            return ALLOWED_NAMES[node.id]
        raise ValueError(f"Use of name '{node.id}' is not allowed.")

    def visit_UnaryOp(self, node: ast.UnaryOp):
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise ValueError(f"Unsupported unary operator: {type(node.op)}")

    def visit_BinOp(self, node: ast.BinOp):
        left = self.visit(node.left)
        right = self.visit(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ZeroDivisionError("Division by zero")
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            if right == 0:
                raise ZeroDivisionError("Division by zero")
            return left // right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Pow):
            return left ** right
        raise ValueError(f"Unsupported binary operator: {type(node.op)}")

    def visit_Call(self, node: ast.Call):
        func = self.visit(node.func)
        args = [self.visit(arg) for arg in node.args]
        if callable(func):
            return func(*args)
        raise ValueError("Function call not allowed.")

    def generic_visit(self, node):
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")


class CalculatorTool(BaseTool):
    """Tool for performing mathematical computations safely."""
    name = "calculator"
    description = "Perform mathematical calculations safely. Supports arithmetic (+, -, *, /), powers (**), percentages (e.g. 25% of 80000), and math functions (sqrt, round, etc.)."
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Mathematical expression to evaluate, e.g. '25% of 80,000' or '(15 * 4) + 120'."
            }
        },
        "required": ["expression"]
    }

    async def execute(self, expression: str, **kwargs: Any) -> str:
        """Evaluate mathematical expression."""
        try:
            expr = expression.strip()

            # ── Handle Average requests e.g. "average of 10, 20, 30, 40" ─────
            avg_match = re.search(r'(?:average|mean)\s+(?:of\s+)?([0-9\s,\.]+)', expr, re.IGNORECASE)
            if avg_match:
                nums = [float(n.strip()) for n in avg_match.group(1).replace(',', ' ').split() if n.strip()]
                if nums:
                    avg_res = sum(nums) / len(nums)
                    if avg_res.is_integer(): avg_res = int(avg_res)
                    return f"Result: {avg_res} (Average of {len(nums)} numbers)"

            # ── Handle Ratio requests e.g. "ratio of 50 to 200" or "ratio 50:200" ──
            ratio_match = re.search(r'(?:ratio\s+(?:of\s+)?|)(\d+(?:\.\d+)?)\s*(?:to|:)\s*(\d+(?:\.\d+)?)', expr, re.IGNORECASE)
            if ratio_match and ("ratio" in expr.lower() or ":" in expr):
                a, b = float(ratio_match.group(1)), float(ratio_match.group(2))
                if b != 0:
                    gcd_val = math.gcd(int(a), int(b)) if a.is_integer() and b.is_integer() else None
                    if gcd_val:
                        simplified = f"{int(a)//gcd_val}:{int(b)//gcd_val}"
                    else:
                        simplified = f"{a/b:.4f}"
                    return f"Result: Simplified Ratio = {simplified} (Decimal = {round(a/b, 4)})"

            # Clean commas in numbers like 80,000 -> 80000
            expr = re.sub(r'(\d+),(\d+)', r'\1\2', expr)

            # Convert percentage patterns e.g. '25% of 80000' -> '(25 / 100) * 80000'
            pct_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*%\s*of\s*(\d+(?:\.\d+)?)', re.IGNORECASE)
            expr = pct_pattern.sub(r'(\1 / 100) * \2', expr)

            # Convert standalone percentage e.g. '25%' -> '(25 / 100)'
            expr = re.sub(r'(\d+(?:\.\d+)?)\s*%', r'(\1 / 100)', expr)

            # Replace ^ with **
            expr = expr.replace('^', '**')

            # Parse AST safely (AST AST evaluation — zero unsafe eval execution)
            node = ast.parse(expr, mode='eval')
            evaluator = SafeEvaluator()
            result = evaluator.visit(node)

            # Format result nicely
            if isinstance(result, float) and result.is_integer():
                result = int(result)

            return f"Result: {result}"
        except ZeroDivisionError:
            return "Error: Division by zero is undefined."
        except Exception as e:
            return f"Calculation Error: Could not evaluate '{expression}'. Details: {str(e)}"


"""
KHANX Coding Mode Engine.

Provides specialized code generation, explanation, debugging, optimization, and test suite creation
for 6 major programming languages:
- Python
- Java
- C
- C++
- JavaScript
- SQL

Capabilities:
1. Explain Code (Line-by-line breakdown, data structures, Time & Space complexity)
2. Debug & Fix Errors (Root cause analysis, corrected code, edge cases)
3. Optimize Code (Algorithmic refactoring, memory optimization, complexity comparison)
4. Generate Code (Production-ready implementation, type safety, error handling)
5. Create Test Cases (Comprehensive unit test suites for edge cases, boundaries, invalid inputs)

Safety Guarantee:
- Code is NEVER executed automatically. Formatted code blocks are presented for user review.
- Existing RAG and chat pipelines remain 100% unchanged.
"""

import re
from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass
class CodingModeConfig:
    """Configured Coding Mode request."""
    task_type: str             # 'explain', 'debug_fix', 'optimize', 'generate', 'test_cases'
    language: str              # 'Python', 'Java', 'C', 'C++', 'JavaScript', 'SQL', 'Auto'
    directive: str             # Prompt overlay directive
    query_hint: str            # Original query text


# ── Language Detection Patterns ──────────────────────────────────────────────
LANGUAGE_PATTERNS: List[Tuple[str, List[str]]] = [
    ("Python", [r"\bpython\b", r"\bpy\b", r"\bdef\s+\w+\b", r"\bimport\s+\w+\b", r"\bpytest\b"]),
    ("Java", [r"\bjava\b", r"\bpublic\s+class\b", r"\bSystem\.out\.print\b", r"\bJUnit\b"]),
    ("C++", [r"\bc\+\+(\b|\s|$)", r"\bcpp\b", r"#include\s*<iostream>", r"\bstd::", r"vector<\w+>"]),
    ("C", [r"\bc\b(?![\+\#])", r"#include\s*<stdio\.h>", r"\bmalloc\b", r"\bprintf\b"]),
    ("JavaScript", [r"\bjavascript\b", r"\bjs\b", r"\btypescript\b", r"\bts\b", r"\bconst\s+\w+\s*=", r"\bconsole\.log\b", r"\bjest\b"]),
    ("SQL", [r"\bsql\b", r"\bpostgres\b", r"\bmysql\b", r"\bsqlite\b", r"\bSELECT\b", r"\bJOIN\b"]),
]

# ── Task Directives ──────────────────────────────────────────────────────────
TASK_RULES = [
    # Test Cases Creation
    ("test_cases",
     "CODING MODE — TEST CASE CREATION:\n"
     "Create a comprehensive unit test suite.\n"
     "Structure your response as:\n"
     "1. **Test Strategy & Coverage Overview** (Happy paths, edge cases, boundary values, invalid inputs)\n"
     "2. **Complete Test Suite Code** (Use standard testing framework: `pytest` for Python, `JUnit` for Java, `GoogleTest/assert` for C/C++, `Jest` for JavaScript, test queries for SQL)\n"
     "3. **Expected Test Execution Results**\n"
     "\nSAFETY DIRECTIVE: Do not execute generated code automatically. Present code clearly in formatted markdown code blocks for user review.",
     [
         (r"\b(test\s+cases?|unit\s+tests?|test\s+suite|tests?|pytest|junit|jest)\b", 1.0),
         (r"\bwrite\s+tests?\s+for\b", 0.95),
         (r"\bcreate\s+test\s+(suite|cases?)\b", 0.95),
     ]),

    # Debug & Fix Errors
    ("debug_fix",
     "CODING MODE — DEBUG & FIX ERRORS:\n"
     "Systematically diagnose and fix code errors.\n"
     "Structure your response as:\n"
     "1. **Root Cause Analysis:** Explain why the bug or error occurs\n"
     "2. **Corrected Code:** Provide the complete, bug-free code with inline comments explaining the fixes\n"
     "3. **Fix Explanation:** Key changes made and why they resolve the issue\n"
     "4. **Edge Cases to Watch For:** Boundary conditions or traps\n"
     "\nSAFETY DIRECTIVE: Do not execute generated code automatically. Present code clearly in formatted markdown code blocks for user review.",
     [
         (r"\b(debug|fix|diagnose|resolve)\b.*(error|bug|issue|exception|crash|fault)?", 1.0),
         (r"\b(syntax\s+error|runtime\s+error|nullpointerexception|segmentation\s+fault|typeerror|indexerror)\b", 0.95),
         (r"\bwhy\s+is\s+my\s+code\s+(failing|crashing|not\s+working|broken)\b", 0.95),
         (r"\bfix\s+(this|my)\s+code\b", 0.9),
     ]),

    # Optimize Code
    ("optimize",
     "CODING MODE — CODE OPTIMIZATION & REFACTORING:\n"
     "Optimize the code for performance, memory, and readability.\n"
     "Structure your response as:\n"
     "1. **Bottleneck Analysis:** Identify performance/memory inefficiencies\n"
     "2. **Optimized Code:** Provide the clean, refactored implementation with inline comments\n"
     "3. **Complexity Comparison Table:** Compare Original vs Optimized (Time Complexity $O(\\cdot)$ & Space Complexity $O(\\cdot)$)\n"
     "4. **Key Optimization Techniques Applied**\n"
     "\nSAFETY DIRECTIVE: Do not execute generated code automatically. Present code clearly in formatted markdown code blocks for user review.",
     [
         (r"\b(optimize|refactor|improve\s+performance|make\s+faster|reduce\s+memory|clean\s+up)\b.*(code|function|script|query)?", 1.0),
         (r"\btime\s+complexity\s+optimization\b", 0.95),
         (r"\boptimize\s+(this|my)\s+(code|function|sql|script)\b", 0.9),
     ]),

    # Explain Code
    ("explain",
     "CODING MODE — CODE EXPLANATION:\n"
     "Provide a detailed technical breakdown of the code.\n"
     "Structure your response as:\n"
     "1. **High-Level Purpose:** Overview of what the code accomplishes\n"
     "2. **Line-by-Line / Section Breakdown:** Clear explanation of key logic and algorithms\n"
     "3. **Data Structures & Algorithms Used**\n"
     "4. **Time & Space Complexity:** Big-O notation ($O(\\cdot)$) for time and auxiliary space\n"
     "\nSAFETY DIRECTIVE: Do not execute generated code automatically. Present code clearly in formatted markdown code blocks for user review.",
     [
         (r"\bexplain\s+.*(code|function|script|algorithm|sql|program|query|implementation)\b", 1.0),
         (r"\bhow\s+does\s+this\s+code\s+work\b", 0.95),
         (r"\bwalk\s+me\s+through\s+this\s+code\b", 0.9),
         (r"\bcode\s+breakdown\b", 0.9),
     ]),

    # Generate Code
    ("generate",
     "CODING MODE — CODE GENERATION:\n"
     "Write clean, production-grade code.\n"
     "Structure your response as:\n"
     "1. **Approach Overview:** Brief explanation of design choices\n"
     "2. **Production-Ready Code:** Full, self-contained implementation with type annotations, comments, and proper error handling\n"
     "3. **Usage Example & Output:** Clear demonstration showing how to run the code and expected output\n"
     "\nSAFETY DIRECTIVE: Do not execute generated code automatically. Present code clearly in formatted markdown code blocks for user review.",
     [
         (r"\b(write|create|generate|build|implement|code)\b.*(function|class|script|program|sql|api|query|code)", 1.0),
         (r"\bhow\s+to\s+(write|code|implement|build)\b", 0.85),
         (r"\bgive\s+me\s+(the\s+)?code\s+for\b", 0.9),
     ]),
]



class CodingModeEngine:
    """Engine for detecting coding tasks, programming languages, and generating structured coding overlays."""

    def detect_language(self, text: str) -> str:
        """Detect programming language from text or code snippets."""
        for lang, patterns in LANGUAGE_PATTERNS:
            for pat in patterns:
                if re.search(pat, text, re.IGNORECASE):
                    return lang
        return "Universal"

    def detect_coding_config(self, message: str, mode_param: str = "chat") -> Optional[CodingModeConfig]:
        """Detect if query is a Coding Mode request or if explicit mode='coding' was set."""
        if not message or not message.strip():
            return None

        msg = message.strip()
        lang = self.detect_language(msg)

        # Check task pattern rules
        for task_type, directive, patterns in TASK_RULES:
            for pattern, weight in patterns:
                if re.search(pattern, msg, re.IGNORECASE):
                    return CodingModeConfig(
                        task_type=task_type,
                        language=lang,
                        directive=directive,
                        query_hint=msg
                    )

        # If explicit mode parameter is "coding"
        if mode_param == "coding":
            return CodingModeConfig(
                task_type="generate",
                language=lang,
                directive=TASK_RULES[-1][1],  # Code generation directive
                query_hint=msg
            )

        return None

    def build_coding_system_prompt(self, config: CodingModeConfig) -> str:
        """Build coding mode system prompt overlay."""
        lang_str = f" ({config.language})" if config.language != "Universal" else ""
        return (
            f"\n\n=== CODING MODE ACTIVE [{config.task_type.upper()}{lang_str.upper()}] ===\n"
            f"Programming Language Target: {config.language}\n"
            f"{config.directive}\n"
            "============================================================"
        )


# Singleton
coding_mode_engine = CodingModeEngine()

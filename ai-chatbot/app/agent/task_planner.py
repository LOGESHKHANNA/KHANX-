"""
KHANX Multi-Step Task Planning & Execution Engine.

Flow: User Goal -> Plan -> Subtasks -> Execute -> Track Progress -> Final Result.

1. Identifies complex multi-step user goals.
2. Decomposes goals into structured subtasks with explicit states: PENDING, IN_PROGRESS, COMPLETED, FAILED.
3. Sequentially executes subtasks and tracks progress with visual status indicators.
4. Synthesizes all subtask results into a final result report.
5. Skips simple questions completely and falls back to standard chatbot behavior if planning is unavailable.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum


class TaskState(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class SubTask:
    id: str
    title: str
    description: str
    status: TaskState = TaskState.PENDING
    result: Optional[str] = None


@dataclass
class TaskPlan:
    goal: str
    subtasks: List[SubTask] = field(default_factory=list)
    current_step_index: int = 0
    is_completed: bool = False

    def render_progress_tracker(self) -> str:
        """Render a clean Markdown progress checklist showing subtask states."""
        lines = [f"### 📋 **Task Execution Plan**: *{self.goal}*\n"]
        for st in self.subtasks:
            if st.status == TaskState.COMPLETED:
                icon = "`[x]` ✅"
            elif st.status == TaskState.IN_PROGRESS:
                icon = "`[/]` ⏳"
            elif st.status == TaskState.FAILED:
                icon = "`[!]` ❌"
            else:
                icon = "`[ ]` ⏸️"

            lines.append(f"- {icon} **{st.title}** (`{st.status.value}`): {st.description}")

        return "\n".join(lines)


class TaskPlanner:
    """Task Planning and Execution Engine for complex multi-step user requests."""

    def should_plan_task(self, query: str, mode_param: str = "chat") -> bool:
        """Determine if query warrants a multi-step task plan (skips simple questions)."""
        if mode_param in ("plan", "task", "workflow"):
            return True

        if not query or len(query.strip()) < 20:
            return False

        complex_patterns = [
            r"\b(build|create|develop|implement|design|write)\s+a\s+(complete|full|entire|multi-step)\b",
            r"\b(plan|step-by-step|roadmap|workflow|stage|phases?)\b.*(for|to|achieve|build)?",
            r"\b(first|second|then|finally|next)\b.*(and|after|then)\b",
            r"\b(research|analyze|compare|summarize|document)\s+and\s+(generate|write|build|create)\b",
        ]

        for pat in complex_patterns:
            if re.search(pat, query, re.IGNORECASE):
                return True

        return False

    def create_plan(self, goal: str) -> TaskPlan:
        """Decompose a complex user goal into structured subtasks."""
        cleaned_goal = goal.strip()

        # Build 3-4 structured subtasks based on query intent
        subtasks = []

        if re.search(r"\b(code|build|develop|api|app|program)\b", cleaned_goal, re.IGNORECASE):
            subtasks = [
                SubTask("st_1", "Requirement Analysis & Architecture", "Outline core components, data models, and API interfaces."),
                SubTask("st_2", "Core Code Implementation", "Write functional code blocks for primary logic and modules."),
                SubTask("st_3", "Error Handling & Optimization", "Implement validation, edge-case checks, and performance refactoring."),
                SubTask("st_4", "Verification & Test Cases", "Create unit test assertions and usage documentation.")
            ]
        elif re.search(r"\b(research|compare|document|report|analysis)\b", cleaned_goal, re.IGNORECASE):
            subtasks = [
                SubTask("st_1", "Information Gathering & Data Retrieval", "Fetch relevant context from uploaded documents and web sources."),
                SubTask("st_2", "Comparative Analysis & Key Point Extraction", "Structure findings, compare metrics, and identify key takeaways."),
                SubTask("st_3", "Report Synthesis & Citation Grounding", "Draft comprehensive, cited research findings with source attribution.")
            ]
        else:
            subtasks = [
                SubTask("st_1", "Task Breakdown & Scope Definition", "Identify prerequisites, goals, and key deliverables."),
                SubTask("st_2", "Phase 1 Execution", "Execute initial research, drafting, or computation."),
                SubTask("st_3", "Phase 2 Refinement & Final Review", "Consolidate results, polish structure, and verify completeness.")
            ]

        return TaskPlan(goal=cleaned_goal, subtasks=subtasks)

    def build_planner_system_prompt(self, plan: TaskPlan) -> str:
        """Build system prompt overlay instructing LLM to execute planned subtasks with state tracking."""
        tracker_md = plan.render_progress_tracker()

        subtask_directives = []
        for i, st in enumerate(plan.subtasks, 1):
            subtask_directives.append(f"Phase {i} ({st.title}): {st.description}")

        directives_str = "\n".join(subtask_directives)

        return (
            "\n\n=== MULTI-STEP TASK PLANNER ACTIVE ===\n"
            f"{tracker_md}\n\n"
            "EXECUTION DIRECTIVES:\n"
            "1. Execute each planned subtask sequentially.\n"
            "2. Mark progress and state for each subtask explicitly in your structured output.\n"
            "3. Conclude with a unified Final Result report synthesizing all completed subtask outputs.\n\n"
            "PLANNED SUBTASKS TO EXECUTE:\n"
            f"{directives_str}\n"
            "============================================================"
        )


# Singleton
task_planner = TaskPlanner()

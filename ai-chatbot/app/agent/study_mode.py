"""
KHANX Study Mode Engine.

Provides an interactive learning environment grounded in existing ChromaDB document RAG.

Supported Study Asset Generation & Features:
1. Summaries (Key points, formulas, definitions, TL;DR)
2. MCQs (Multiple choice questions with 4 options & detailed answer keys)
3. Flashcards (Front/Back Q&A study cards)
4. Viva Questions (Oral exam / interview style conceptual questions with high-score criteria)
5. Short Questions (2-3 mark direct questions & model answers)
6. Long Questions (5-10 mark structured essay/problem questions & marking schemes)
7. Topic Explanations (Interactive step-by-step breakdown with analogies & self-check)
8. Answer Evaluation (Objective 0-10 scoring, strengths, missing points & model answer)
9. Interactive Teaching (Socratic step-by-step guided learning)

Grounding:
- Automatically uses existing ChromaDB vector search (`search_knowledge_base`) to retrieve
  uploaded study material when available for user context.
"""

import re
from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class StudyModeConfig:
    """Configured study mode asset request."""
    asset_type: str            # e.g., 'mcq', 'flashcard', 'viva', 'short_q', 'long_q', 'summary', 'explanation', 'answer_eval', 'interactive'
    directive: str             # Prompt overlay for study asset generation
    query_hint: str            # Query text for RAG retrieval
    is_answer_eval: bool = False


# ── Pattern Rules for Study Asset Detection ──────────────────────────────────
STUDY_RULES = [
    # Answer Evaluation
    ("answer_eval",
     "STUDY MODE — ANSWER EVALUATION: Thoroughly evaluate the user's submitted answer.\n"
     "Structure your response as:\n"
     "1. **Score:** X/10 with brief rationale\n"
     "2. **Key Strengths:** What the user got right\n"
     "3. **Missing / Inaccurate Points:** Gaps or misunderstandings\n"
     "4. **Model Answer:** High-scoring exemplar answer\n"
     "5. **Follow-up Practice Question:** To test their improved understanding.",
     [
         (r"\b(evaluate|grade|rate|check|score|review)\s+(my\s+)?(answer|response|solution)\b", 1.0),
         (r"\bis\s+this\s+(answer|response|solution)\s+(correct|right|good)\b", 0.95),
         (r"\bhere\s+is\s+my\s+(answer|response)\b", 0.9),
     ]),

    # MCQs
    ("mcq",
     "STUDY MODE — MCQ GENERATION: Create 4–5 high-quality Multiple Choice Questions (MCQs).\n"
     "For each question:\n"
     "- State the Question clearly\n"
     "- Provide Options A, B, C, D\n"
     "- Highlight the **Correct Answer**\n"
     "- Give a brief **Explanation** of why the answer is correct and why distractor options are wrong.",
     [
         (r"\b(generate|create|make|give\s+me)\s+.*(mcqs?|multiple\s+choice\s+questions?)\b", 1.0),
         (r"\b(mcqs?|multiple\s+choice)\s+(on|about|for)\b", 0.95),
         (r"\bquiz\s+me\s+with\s+(mcqs?|options)\b", 0.95),
     ]),

    # Flashcards
    ("flashcard",
     "STUDY MODE — FLASHCARD GENERATION: Create 5–8 interactive Flashcards.\n"
     "Format each card as:\n"
     "🎴 **[Card N]**\n"
     "- **Front (Prompt/Term):** [Question or Term]\n"
     "- **Back (Definition/Answer):** [Concise, memorable explanation]\n"
     "Focus on high-yield exam concepts, formulas, and key definitions.",
     [
         (r"\b(generate|create|make|give\s+me)\s+.*flashcards?\b", 1.0),
         (r"\bflashcards?\s+(on|about|for|from)\b", 0.95),
         (r"\bstudy\s+cards?\b", 0.9),
     ]),

    # Viva Questions
    ("viva",
     "STUDY MODE — VIVA VOCE / ORAL EXAM: Generate 4–5 examiner-level Viva Voce questions.\n"
     "For each viva question:\n"
     "- State the **Examiner Question** (probing, conceptual, or practical)\n"
     "- List **Key Technical Points** expected in a top-grade candidate response\n"
     "- Provide a **Model Viva Answer** (concise, professional oral response).",
     [
         (r"\b(viva|viva\s+voce|oral\s+exam)\s*(questions?|prep|practice)?\b", 1.0),
         (r"\b(prepare|practice)\s+me\s+for\s+viva\b", 0.95),
     ]),

    # Short Questions
    ("short_q",
     "STUDY MODE — SHORT ANSWER QUESTIONS (2–3 Marks): Generate 4–5 short-answer exam questions.\n"
     "Format each question as:\n"
     "- **Q[N] [2-3 Marks]:** Question statement\n"
     "- **Model Answer:** Direct 2–4 sentence technical answer with key keywords highlighted.",
     [
         (r"\b(short\s+questions?|short\s+answers?|2\s*marks?|3\s*marks?)\b", 1.0),
         (r"\bshort\s+q&a\b", 0.95),
     ]),

    # Long Questions
    ("long_q",
     "STUDY MODE — LONG ESSAY / ANALYTICAL QUESTIONS (5–10 Marks): Generate 2–3 structured long questions.\n"
     "Format each question as:\n"
     "- **Question [5-10 Marks]:** Comprehensive problem statement\n"
     "- **Marking Scheme Breakdown:** Key sections & point allocation\n"
     "- **Structured Model Answer Outline:** Headings, diagram guidance (if applicable), and thorough explanation.",
     [
         (r"\b(long\s+questions?|essay\s+questions?|5\s*marks?|10\s*marks?|detailed\s+questions?)\b", 1.0),
         (r"\blong\s+q&a\b", 0.95),
     ]),

    # Summaries
    ("summary",
     "STUDY MODE — STUDY SUMMARY & REVISION SHEET: Generate a comprehensive study summary.\n"
     "Include:\n"
     "1. **Core Concept Overview**\n"
     "2. **Essential Formulas / Key Definitions**\n"
     "3. **High-Yield Revision Bullet Points**\n"
     "4. **Common Exam Pitfalls to Avoid**\n"
     "5. **One-Line TL;DR Summary**.",
     [
         (r"\b(study\s+summary|revision\s+notes?|cheat\s+sheet|chapter\s+summary|revision\s+summary)\b", 1.0),
         (r"\bsummarize\s+(this\s+)?(chapter|unit|paper|document|topic)\s+for\s+study\b", 0.95),
     ]),

    # Topic Explanations
    ("explanation",
     "STUDY MODE — TOPIC EXPLANATION: Provide an engaging, in-depth topic breakdown.\n"
     "Structure as:\n"
     "1. **Intuitive Analogy:** Relate to real-world experience\n"
     "2. **Core Mechanics:** Step-by-step breakdown\n"
     "3. **Technical Nuances / Edge Cases**\n"
     "4. **Quick Self-Check Question:** To verify understanding.",
     [
         (r"\bexplain\s+topic\b", 1.0),
         (r"\bdeep\s+dive\s+(into\s+)?(topic|concept)\b", 0.95),
         (r"\bbreakdown\s+(this|the)\s+topic\b", 0.9),
     ]),

    # Interactive Teaching
    ("interactive",
     "STUDY MODE — INTERACTIVE TEACHER: Act as a master tutor.\n"
     "Teach the topic step-by-step. Present one section at a time, check understanding "
     "with a quick question, and adapt to the student's progress.",
     [
         (r"\bstudy\s+mode\b", 1.0),
         (r"\btutor\s+me\b", 0.95),
         (r"\bteach\s+me\s+interactively\b", 0.95),
     ]),
]


class StudyModeEngine:
    """Engine for detecting study requests, executing RAG retrieval, and generating prompt overlays."""

    def detect_study_config(self, message: str, mode_param: str = "chat") -> Optional[StudyModeConfig]:
        """Detect if query is a study mode request or if explicit mode='study' was passed."""
        if not message or not message.strip():
            return None

        msg = message.strip()

        # Check explicit patterns
        for asset_type, directive, patterns in STUDY_RULES:
            for pattern, weight in patterns:
                if re.search(pattern, msg, re.IGNORECASE):
                    return StudyModeConfig(
                        asset_type=asset_type,
                        directive=directive,
                        query_hint=msg,
                        is_answer_eval=(asset_type == "answer_eval")
                    )

        # If explicit mode parameter is "study" but no sub-pattern matched
        if mode_param == "study":
            return StudyModeConfig(
                asset_type="interactive",
                directive=STUDY_RULES[-1][1],  # Interactive tutor directive
                query_hint=msg
            )

        return None

    def build_study_system_prompt(self, config: StudyModeConfig, rag_context: Optional[str] = None) -> str:
        """Build study mode system prompt with RAG document grounding."""
        prompt = f"\n\n=== STUDY MODE ACTIVE [{config.asset_type.upper()}] ===\n{config.directive}"

        if rag_context and rag_context.strip():
            prompt += (
                "\n\nGROUNDING DIRECTIVE:\n"
                "You are in STUDY MODE grounded in the user's uploaded study materials.\n"
                "You MUST base your generated study assets (summaries, MCQs, flashcards, viva/short/long questions, "
                "topic explanations, answer evaluations) strictly on the retrieved document context below.\n"
                "Cite document filenames when referencing specific facts.\n\n"
                f"=== RETRIEVED STUDY MATERIAL (RAG CONTEXT) ===\n{rag_context}\n"
                "=================================================="
            )
        else:
            prompt += (
                "\n\nGROUNDING NOTE:\n"
                "No uploaded document context was found for this specific query. "
                "Provide high-quality educational study material based on general academic knowledge, "
                "and clearly inform the user that they can upload study documents for document-grounded study assets."
            )

        return prompt


# Singleton
study_mode_engine = StudyModeEngine()

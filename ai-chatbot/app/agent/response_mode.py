"""
KHANX Response Mode Detector & Prompt Overlays

Detects 10 optional response modes from user message patterns (zero LLM cost).
Injects a focused behavioral directive into the system prompt to shape HOW
KHANX structures its answer — without changing WHAT tools it selects.

Modes:
  explain    — Clear step-by-step breakdown of a concept
  teach      — Guided lesson with examples and exercises
  summarize  — Condense into key points / TL;DR
  compare    — Side-by-side structured comparison
  analyze    — Critical evaluation with pros/cons and evidence
  research   — Comprehensive multi-source synthesis
  code       — Produce clean, documented code
  debug      — Diagnose and fix errors methodically
  quiz       — Generate questions to test understanding
  interview  — Conduct a mock interview session
  (None)     — Normal chat, no overlay
"""

import re
from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass
class ResponseMode:
    """Detected response mode and its behavioral directive."""
    name: str           # Mode label (e.g. "explain")
    directive: str      # System prompt overlay to inject
    confidence: float   # 0.0–1.0
    explicit: bool      # True if user explicitly requested the mode


# ── Mode definitions: (name, directive, [(pattern, weight), ...]) ─────────────
MODE_RULES: List[Tuple[str, str, List[Tuple[str, float]]]] = [

    ("quiz",
     "RESPONSE MODE — QUIZ: Generate 4–6 well-structured questions that test the user's understanding "
     "of the topic they asked about. Vary question difficulty (easy → hard). "
     "After listing questions, invite the user to answer so you can give feedback.",
     [
         (r"\bquiz\s+me\b", 1.0),
         (r"\btest\s+my\s+(knowledge|understanding)\b", 1.0),
         (r"\bask\s+me\s+(some\s+)?(questions?|quizzes?)\b", 1.0),
         (r"\b(create|generate|give)\s+(me\s+)?(a\s+)?quiz\b", 0.95),
     ]),

    ("interview",
     "RESPONSE MODE — INTERVIEW: Conduct a focused mock interview on the topic. "
     "Ask one thoughtful interview question at a time, wait for the user's response, "
     "give brief structured feedback, then ask the next question. "
     "Maintain a professional but encouraging tone.",
     [
         (r"\b(mock\s+)?interview\s+me\b", 1.0),
         (r"\bpractice\s+(interview|interviewing)\b", 1.0),
         (r"\binterview\s+(prep|preparation|practice|simulation)\b", 0.95),
         (r"\bact\s+as\s+(a\s+)?(interviewer|recruiter)\b", 0.95),
     ]),

    ("debug",
     "RESPONSE MODE — DEBUG: Systematically diagnose the issue. "
     "First identify the root cause, then explain WHY it happens, "
     "then provide a clear corrected solution with inline comments. "
     "Mention edge cases or related pitfalls to watch for.",
     [
         (r"\b(debug|fix|diagnose)\s+(this\s+)?(error|bug|issue|problem|crash|exception)\b", 1.0),
         (r"\b(why\s+(is|does|am|are)\s+.{3,40}(fail|crash|error|break|wrong|not work))\b", 0.9),
         (r"\b(traceback|stack trace|exception|runtime error|syntax error|attribute error|type error|key error)\b", 0.85),
         (r"\b(not working|broken|failing|incorrect output|unexpected (result|behavior))\b", 0.8),
         (r"\bwhat('s| is) wrong with\b", 0.9),
     ]),

    ("code",
     "RESPONSE MODE — CODE: Write clean, production-quality code. "
     "Structure your output as: (1) brief explanation of the approach, "
     "(2) the complete code block with inline comments, "
     "(3) a usage example. Keep explanations concise — let the code speak.",
     [
         (r"\b(write|create|generate|build|implement|code)\b.{0,40}\b(function|class|script|module|program|api)\b", 0.95),
         (r"\b(give|show)\s+me\s+(the\s+)?(code|implementation|solution|script)\b", 0.95),
         (r"\bhow\s+(do\s+i|to|can\s+i)\s+(implement|write|build|create)\b", 0.8),
         (r"\bcode\s+(for|to|that)\b", 0.85),
     ]),

    ("teach",
     "RESPONSE MODE — TEACH: Structure your answer as a mini-lesson. "
     "Start with the core concept, explain it simply, give 1–2 real-world examples, "
     "then end with a short comprehension check question to reinforce learning.",
     [
         (r"\bteach\s+me\b", 1.0),
         (r"\bhelp\s+me\s+(learn|understand)\b", 0.95),
         (r"\bwalk\s+me\s+through\b", 0.9),
         (r"\bexplain\s+.{0,30}\blike\s+i('m|\s+am)\s+(a\s+)?(beginner|noob|5|five|kid|student)\b", 0.95),
         (r"\bI('m|\s+am)\s+(new\s+to|learning|trying\s+to\s+understand)\b", 0.8),
     ]),

    ("summarize",
     "RESPONSE MODE — SUMMARIZE: Provide a tight, structured summary. "
     "Use bullet points for key facts. Aim for maximum information density with minimum words. "
     "End with a one-sentence TL;DR.",
     [
         (r"\b(summarize|summarise|summary|tl;?dr|tldr|brief(ly)?|in\s+short|in\s+brief)\b", 1.0),
         (r"\bkey\s+(points?|takeaways?|highlights?)\b", 0.9),
         (r"\bshorten\b.{0,30}\b(text|this|response|answer)\b", 0.9),
         (r"\bgive\s+me\s+(a\s+)?(brief|short|quick)\s+(overview|summary|rundown)\b", 0.9),
         (r"\bcut\s+(to\s+the\s+chase|it\s+short)\b", 0.85),
     ]),

    ("compare",
     "RESPONSE MODE — COMPARE: Structure your answer as a clear comparison. "
     "Use a table or labeled sections (similarities, differences, when to use each). "
     "End with a recommendation or verdict based on the context.",
     [
         (r"\bcompare\b.{0,40}\b(vs?\.?|versus|and|with|against)\b", 1.0),
         (r"\b(difference|differences|distinction)\s+between\b", 1.0),
         (r"\bwhich\s+is\s+(better|faster|more|best)\b", 0.9),
         (r"\b(pros?\s+and\s+cons?|advantages?\s+and\s+disadvantages?)\b", 0.9),
         (r"\b(X\s+vs\s+Y|A\s+vs\s+B)\b", 0.85),
     ]),

    ("analyze",
     "RESPONSE MODE — ANALYZE: Provide a structured analytical response. "
     "Cover: (1) overview, (2) key strengths, (3) weaknesses/risks, (4) implications or recommendations. "
     "Back claims with reasoning. Be objective and evidence-driven.",
     [
         (r"\b(analyze|analyse|evaluation|evaluate|assess|assessment)\b", 1.0),
         (r"\b(what\s+are\s+the\s+(implications?|impacts?|consequences?|effects?))\b", 0.9),
         (r"\bcritically\s+(review|assess|examine|evaluate)\b", 0.95),
         (r"\b(breakdown|break\s+down)\b.{0,30}\b(this|the|my)\b", 0.85),
         (r"\bwhat\s+(does|do|is)\s+.{3,40}\s+(tell|suggest|indicate|mean for)\b", 0.8),
     ]),

    ("research",
     "RESPONSE MODE — RESEARCH: Provide a comprehensive, well-organized research response. "
     "Cover background, current understanding, key debates or findings, and future outlook. "
     "Cite specific concepts, frameworks, or named examples. Structure with clear headings.",
     [
         (r"\b(research|comprehensive|in-depth|deep\s+dive|thorough|detailed)\s+(overview|analysis|explanation|study|survey|review|paper|report)?\b", 1.0),
         (r"\b(state\s+of\s+the\s+art|literature\s+review|literature\s+survey|survey\s+of)\b", 1.0),
         (r"\bwhat\s+(is|are)\s+the\s+(history|evolution|background|origins?)\s+of\b", 0.9),
         (r"\bcomprehensive\s+(guide|report|breakdown|summary)\b", 0.95),
         (r"\bresearch\s+(on|about|into)\b", 0.9),
     ]),


    ("explain",
     "RESPONSE MODE — EXPLAIN: Give a clear, intuitive explanation. "
     "Start with a one-sentence definition, then build up with an analogy or concrete example. "
     "Avoid jargon unless you define it. Structure logically from basics to nuance.",
     [
         (r"\b(explain|elaborate|clarify|describe)\b", 0.85),
         (r"\b(how\s+does|how\s+do)\s+.{3,50}\s+(work|function|operate)\b", 0.85),
         (r"\bwhy\s+(does|do|is|are|did)\b.{3,60}\b(work|happen|occur|exist|matter)\b", 0.8),
         (r"\bcould\s+you\s+(explain|clarify|describe|elaborate)\b", 0.9),
         (r"\bI\s+(don't|do\s+not)\s+understand\b", 0.85),
         (r"\bwhat\s+does\s+.{3,50}\s+mean\b", 0.85),
         (r"\bwhat\s+is\s+the\s+(concept|theory|principle)\s+of\b", 0.85),
     ]),

]


class ResponseModeDetector:
    """Fast pattern-based response mode detector — zero LLM cost."""

    def detect(self, message: str) -> Optional[ResponseMode]:
        """Detect the most appropriate response mode from the user message.

        Returns None for normal chat (no mode overlay needed).
        """
        if not message or not message.strip() or len(message.strip()) < 4:
            return None

        msg = message.strip()
        best_name: Optional[str] = None
        best_score: float = 0.0
        best_directive: str = ""
        best_explicit: bool = False

        for name, directive, patterns in MODE_RULES:
            total = 0.0
            explicit = False
            for pattern, weight in patterns:
                if re.search(pattern, msg, re.IGNORECASE):
                    total += weight
                    if weight >= 0.9:
                        explicit = True
            if total > best_score:
                best_score = total
                best_name = name
                best_directive = directive
                best_explicit = explicit

        # Only activate a mode if confidence is meaningful
        if best_name and best_score >= 0.75:
            return ResponseMode(
                name=best_name,
                directive=best_directive,
                confidence=round(min(best_score, 1.0), 2),
                explicit=best_explicit
            )

        return None  # Normal chat — no overlay


# Singleton
response_mode_detector = ResponseModeDetector()

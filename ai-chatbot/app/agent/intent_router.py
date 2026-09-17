"""
KHANX Intent Router — Fast Query Intent Classification

Classifies user messages into one of 8 intents using rule-based pattern matching
before any LLM call. Zero-latency for clear queries — only ambiguous queries
optionally get a lightweight LLM classification.

Intents:
- general_chat     : Greetings, opinions, general knowledge, casual conversation
- rag              : Questions about uploaded user documents or files
- web_search       : Current events, news, live/real-time information
- calculation      : Math, percentages, ratios, formulas, unit conversions
- coding           : Writing code, debugging, technical programming help
- document_analysis: Summarize, analyze, extract from a CSV / document
- image_analysis   : Analyze an image, screenshot, diagram, chart
- research         : Deep comprehensive explanations, literature review, multi-source synthesis

Routing contract:
  router = IntentRouter()
  intent = router.classify("what is 25% of 80000")
  # Intent(name='calculation', confidence=0.95, suggested_tool='calculator', hint='...')
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

@dataclass
class Intent:
    """Result of an intent classification."""
    name: str                               # Intent label
    confidence: float                       # 0.0 – 1.0
    suggested_tool: Optional[str] = None   # Recommended first tool to invoke
    hint: str = ""                          # Extra context hint for the orchestrator


# ── Pattern Registry ─────────────────────────────────────────────────────────
# Each entry: (intent_name, suggested_tool, [(regex_pattern, weight), ...])
INTENT_RULES: List[Tuple[str, Optional[str], List[Tuple[str, float]]]] = [

    # ── Image Analysis ──────────────────────────────────────────────────────
    ("image_analysis", "analyze_image", [
        (r"\b(this image|that image|the image|screenshot|diagram|chart|photo|picture|figure)\b", 1.0),
        (r"\banalyze (the |this |that )?(image|picture|photo|screenshot|chart|diagram)\b", 1.0),
        (r"\bwhat (is|does|do|can you see) in (this |the )?(image|photo|picture|screenshot)\b", 1.0),
        (r"\bdescribe (the |this |that )?(image|photo|chart|diagram|figure)\b", 0.9),
        (r"\b(read|ocr|extract text from) (the |this )?(image|screenshot)\b", 0.9),
    ]),

    # ── Image Generation ────────────────────────────────────────────────────
    ("image_generation", "generate_image", [
        (r"\b(generate|create|make|draw|paint)\b.{0,30}\b(image|picture|photo|illustration|drawing|artwork)\b", 0.95),
        (r"\b(show me a picture of|i want an image of|can you generate an image)\b", 0.95),
        (r"\b(an image|a picture|a photo) (of|showing)\b", 0.8),
    ]),

    # ── Calculation ─────────────────────────────────────────────────────────
    ("calculation", "calculator", [
        (r"\b\d+\s*[\+\-\*\/\^]\s*\d+", 0.95),                          # raw expression: 12 * 4
        (r"\b\d+(\.\d+)?\s*%\s*(of)\s*\d+", 0.95),                      # 25% of 80000
        (r"\bwhat\s+is\s+\d.*([\+\-\*\/\^%]|\bplus\b|\btimes\b|\bdivide)", 0.9),
        (r"\b(calculate|compute|solve|evaluate|find the (value|result))\b", 0.85),
        (r"\b(sum|average|mean|median|ratio|percentage|discount|tax|interest|profit|loss) of\b", 0.85),
        (r"\b(how much|how many)\b.{0,40}\b(cost|total|earn|pay|save|spend)\b", 0.75),
        (r"\b(square root|sqrt|log|logarithm|exponent|factorial|derivative|integral)\s*of\b", 0.9),
        (r"\bconvert\b.{0,30}\b(to|into)\b.{0,20}\b(km|kg|lbs|celsius|fahrenheit|meters|inches)\b", 0.8),
    ]),

    # ── Coding ──────────────────────────────────────────────────────────────
    ("coding", "python_interpreter", [
        (r"\b(write|create|generate|build|implement|code|program)\b.{0,30}\b(function|class|script|code|module|api|endpoint|algorithm)\b", 0.9),
        (r"\b(debug|fix|refactor|optimize|review)\b.{0,20}\b(code|function|script|error|bug|exception|traceback)\b", 0.9),
        (r"\b(python|javascript|typescript|java|c\+\+|c#|rust|go|sql|html|css|react|fastapi|django|flask)\b", 0.75),
        (r"\b(syntax error|runtime error|import error|attribute error|key error|type error|index error)\b", 0.9),
        (r"\bhow (do i|to|can i)?\s*(implement|write|use|call|make|build|create)\b.{0,30}\b(in\s+\w+|code|script|function|class)\b", 0.8),
        (r"\b(loop|recursion|array|list|dictionary|hash|stack|queue|tree|graph|sort|search algorithm)\b", 0.7),
        (r"\bexplain (this |the )?code\b", 0.85),
    ]),

    # ── RAG (Document Search) ───────────────────────────────────────────────
    ("rag", "search_knowledge_base", [
        (r"\b(my document|my file|uploaded (file|document|pdf|doc)|the pdf|in the file|from my (pdf|doc|file))\b", 1.0),
        (r"\b(according to|based on|in (the|my) (document|file|pdf|report|contract|notes))\b", 0.95),
        (r"\b(search|find|look up|retrieve) (in|from|within) (my |the )?(documents?|files?|pdf|upload)\b", 0.95),
        (r"\bwhat does (the |my )?(document|file|pdf|report) say\b", 0.95),
        (r"\b(summarize|analyze) (my |the )?(document|file|pdf|report|notes|paper)\b", 0.85),
        (r"\b(in my|from the|extract from) (notes|report|paper|research|thesis|contract)\b", 0.85),
    ]),

    # ── Document Analysis ───────────────────────────────────────────────────
    ("document_analysis", "python_interpreter", [
        (r"\b(analyze|analyse|summarize|summarise) (this |the |my )?(csv|spreadsheet|data|dataset|table)\b", 0.9),
        (r"\b(read|load|parse|process) (the |this |my )?(csv|excel|xlsx|spreadsheet|dataframe)\b", 0.9),
        (r"\b(column|row|header)\b.{0,30}\b(data|csv|table|dataset)\b", 0.8),
        (r"\bdata (analysis|visualization|trends?|statistics?|insights?)\b", 0.8),
        (r"\bhow many (rows|entries|records|items)\b", 0.75),
    ]),

    # ── Web Search ──────────────────────────────────────────────────────────
    ("web_search", "web_search", [
        (r"\b(latest|current|today|this week|this year|right now|as of|breaking news|recent)\b", 0.85),
        (r"\b(news|headlines|update|stock price|weather|score|result|election)\b", 0.85),
        (r"\bwhat (is|are|was|were) (the )?(latest|current|today|recent)\b", 0.9),
        (r"\bwho (won|is leading|is winning|was elected)\b", 0.85),
        (r"\b(search (the web|google|internet|online)|look (it up|online|on the web))\b", 0.95),
        (r"\b(live|real-?time)\b.{0,30}\b(data|price|rate|score)\b", 0.9),
    ]),

    # ── Research ────────────────────────────────────────────────────────────
    ("research", "wikipedia_search", [
        (r"\b(comprehensive|detailed|in-depth|thorough|deep dive|literature review|state of the art)\b", 0.85),
        (r"\b(explain (in detail|thoroughly|comprehensively|step by step))\b", 0.8),
        (r"\b(what (is|are) the (history|origin|evolution|background) of)\b", 0.8),
        (r"\b(compare and contrast|pros and cons|advantages and disadvantages)\b", 0.75),
        (r"\b(research|survey|overview|summary) (on|of|about)\b", 0.8),
        (r"\b(how does .{3,40} work)\b", 0.65),
    ]),
]

GENERAL_CHAT_PATTERNS = [
    r"^(hi|hello|hey|what's up|howdy|good (morning|evening|afternoon))\b",
    r"^(thanks?|thank you|thx|cheers)\b",
    r"\b(who are you|what are you|tell me about yourself|your name)\b",
    r"\b(how are you|how's it going)\b",
    r"^(yes|no|ok|okay|sure|alright|sounds good|got it|perfect)\b",
    r"\b(what do you think|in your opinion|your thoughts)\b",
]


class IntentRouter:
    """Zero-latency rule-based intent classifier with optional LLM fallback for ambiguous queries."""

    def classify(self, message: str, has_uploaded_docs: bool = False) -> Intent:
        """Classify user query into an intent using fast pattern matching.

        Args:
            message: The user's message text.
            has_uploaded_docs: Hint from caller that user has uploaded documents.

        Returns:
            Intent object with name, confidence, suggested_tool, and hint.
        """
        if not message or not message.strip():
            return Intent(name="general_chat", confidence=1.0, hint="Empty message — default to general chat.")

        msg = message.strip()

        # ── Rapid general chat detection (highest priority for short/simple queries) ──
        if len(msg) < 80:
            for pat in GENERAL_CHAT_PATTERNS:
                if re.search(pat, msg, re.IGNORECASE):
                    return Intent(name="general_chat", confidence=0.95, hint="Simple conversational query — no tools needed.")

        # ── Score each intent rule ────────────────────────────────────────────
        scores: dict[str, Tuple[float, Optional[str]]] = {}
        for intent_name, suggested_tool, patterns in INTENT_RULES:
            total_score = 0.0
            for pattern, weight in patterns:
                if re.search(pattern, msg, re.IGNORECASE):
                    total_score += weight
            if total_score > 0:
                scores[intent_name] = (min(total_score, 1.0), suggested_tool)

        # ── No match → general_chat fallback ─────────────────────────────────
        if not scores:
            return Intent(
                name="general_chat",
                confidence=0.7,
                hint="No specific intent pattern matched — using general chat fallback."
            )

        # ── Pick highest scoring intent ───────────────────────────────────────
        best_intent, (best_score, best_tool) = max(scores.items(), key=lambda x: x[1][0])

        # Boost RAG intent if user has documents uploaded
        if has_uploaded_docs and best_intent == "general_chat":
            rag_score = scores.get("rag", (0.0, None))[0]
            if rag_score > 0.3:
                return Intent(name="rag", confidence=rag_score, suggested_tool="search_knowledge_base",
                               hint="User has uploaded documents — boosting RAG intent.")

        return Intent(
            name=best_intent,
            confidence=round(best_score, 2),
            suggested_tool=best_tool,
            hint=f"Pattern-matched intent: {best_intent} (score={best_score:.2f})"
        )

    def get_tool_choice_hint(self, intent: Intent) -> Optional[str]:
        """Map intent to a forced tool choice string for the Groq API, if applicable."""
        if intent.suggested_tool:
            return intent.suggested_tool
        return None


# Singleton instance
intent_router = IntentRouter()

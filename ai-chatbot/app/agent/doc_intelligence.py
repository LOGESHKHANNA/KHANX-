"""
KHANX Advanced Document Intelligence Engine.

Extends document RAG capabilities beyond standard Q&A to provide:
1. Multi-Document Summarization (Executive summary, section breakdowns, key takeaways)
2. Document & Multi-Document Comparison (Side-by-side matrices, similarities, differences, synthesis)
3. Key-Point & Metric Extraction (Structured bullet points, key rules, numerical metrics, citations)
4. Table & Spreadsheet Understanding (Column schema, row analysis, numerical totals, data trends)
5. Contradiction & Inconsistency Detection (Cross-document conflicting statements, opposing dates, mismatched values)

Reuses ChromaDB RAG and vector store infrastructure without breaking existing Q&A functionality.
"""

import re
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple


@dataclass
class DocTaskConfig:
    """Configured Document Intelligence request."""
    task_type: str        # 'summarize', 'compare', 'key_points', 'table_understanding', 'contradiction'
    directive: str        # System prompt overlay directive
    query_hint: str       # Original query text


DOC_TASK_RULES = [
    # 1. Contradiction & Inconsistency Detection
    ("contradiction",
     "DOCUMENT INTELLIGENCE — CONTRADICTION & INCONSISTENCY DETECTION:\n"
     "Analyze the uploaded document(s) to detect conflicting statements, opposing dates/numbers, or mismatching guidelines.\n"
     "Structure your response as:\n"
     "1. **Contradiction Summary Table** (Topic, Source Doc A, Source Doc B, Conflict Type)\n"
     "2. **Detailed Contradiction Breakdown:**\n"
     "   - **Contradiction Topic:** [Topic Name]\n"
     "   - **Statement in `[Doc A]`:** Exact finding/statement\n"
     "   - **Statement in `[Doc B]`:** Conflicting finding/statement\n"
     "   - **Nature of Conflict:** (Direct contradiction, partial mismatch, temporal revision)\n"
     "3. **Impact Assessment & Recommended Resolution**",
     [
         (r"\b(contradiction|contradict|conflicting|inconsisten(cy|t)|discrepan(cy|t)|mismatch)\b", 1.0),
         (r"\bdoes\s+.*\s+contradict\b", 0.95),
         (r"\bfind\s+(conflicts|inconsistencies|differences|contradictions)\b", 0.95),
         (r"\bcheck\s+for\s+(contradictions|conflicts)\b", 0.9),
     ]),

    # 2. Multi-Document & Intra-Document Comparison
    ("compare",
     "DOCUMENT INTELLIGENCE — DOCUMENT COMPARISON:\n"
     "Perform a rigorous side-by-side comparison of the uploaded document(s).\n"
     "Structure your response as:\n"
     "1. **Comparison Matrix Table** (Aspect/Dimension | Document A | Document B | Alignment Status)\n"
     "2. **Core Similarities & Shared Themes**\n"
     "3. **Key Differences & Divergences**\n"
     "4. **Synthesis & Strategic Recommendation**",
     [
         (r"\b(compare|comparison|versus|vs\.?|diff|differences\s+between)\b.*(documents?|files?|pdfs?|reports?)?", 1.0),
         (r"\bcompare\s+.*\s+(and|with|to)\b", 0.95),
         (r"\bhow\s+do\s+these\s+documents\s+differ\b", 0.95),
         (r"\bside\s*by\s*side\s+comparison\b", 0.9),
     ]),

    # 3. Table & Spreadsheet Understanding
    ("table_understanding",
     "DOCUMENT INTELLIGENCE — TABLE & DATA UNDERSTANDING:\n"
     "Examine and interpret tabular data, CSVs, spreadsheets, or embedded tables.\n"
     "Structure your response as:\n"
     "1. **Table Schema & Overview:** Columns, rows, and data scope\n"
     "2. **Structured Table Representation:** Clean Markdown table of the data\n"
     "3. **Key Numerical Insights & Totals:** Highlighting sums, averages, outliers, or key data trends\n"
     "4. **Business / Technical Takeaways**",
     [
         (r"\b(table|spreadsheet|csv|excel|xlsx|matrix|rows\s+and\s+columns|tabular)\b.*(data|understand|analyze|explain|summary)?", 1.0),
         (r"\banalyze\s+this\s+table\b", 0.95),
         (r"\bextract\s+table\b", 0.9),
         (r"\bread\s+the\s+(csv|spreadsheet|table)\b", 0.9),
     ]),

    # 4. Key-Point & Metric Extraction
    ("key_points",
     "DOCUMENT INTELLIGENCE — KEY-POINT EXTRACTION:\n"
     "Extract critical key points, obligations, rules, and numerical metrics from the document(s).\n"
     "Structure your response as:\n"
     "1. **Executive Key Points** (Categorized bullet points with `[Doc Name]` citations)\n"
     "2. **Critical Metrics & Figures** (Key numbers, percentages, dates, deadlines)\n"
     "3. **Obligations & Action Items**\n"
     "4. **Glossary of Key Terms** (if applicable)",
     [
         (r"\b(key\s*points?|key\s*takeaways?|highlights|extract\s+points|main\s+takeaways?|action\s+items)\b", 1.0),
         (r"\bextract\s+(key|important)\s+(points|information|facts|metrics)\b", 0.95),
         (r"\bwhat\s+are\s+the\s+main\s+points\s+in\b", 0.9),
     ]),

    # 5. Summarization
    ("summarize",
     "DOCUMENT INTELLIGENCE — DOCUMENT SUMMARIZATION:\n"
     "Provide a comprehensive, high-density summary of the document(s).\n"
     "Structure your response as:\n"
     "1. **Executive Summary** (2–3 concise paragraph overview)\n"
     "2. **Section / Topic Breakdown** (Structured headings summarizing each major part)\n"
     "3. **Essential Conclusions**\n"
     "4. **TL;DR Summary** (1–2 sentences)",
     [
         (r"\b(summarize|summary|overview|abstract|synopsis|recap)\b.*(document|file|pdf|report|all)?", 1.0),
         (r"\bgive\s+me\s+a\s+summary\s+of\b", 0.95),
         (r"\bsummarize\s+(this|my|the)\s+(document|file|pdf|report)\b", 0.9),
     ]),
]


class DocIntelligenceEngine:
    """Engine for routing document tasks and building multi-document grounded prompts."""

    def detect_doc_task(self, message: str, mode_param: str = "chat") -> Optional[DocTaskConfig]:
        """Detect document intelligence task type from query or explicit mode parameter."""
        if not message or not message.strip():
            return None

        msg = message.strip()

        for task_type, directive, patterns in DOC_TASK_RULES:
            for pattern, weight in patterns:
                if re.search(pattern, msg, re.IGNORECASE):
                    return DocTaskConfig(
                        task_type=task_type,
                        directive=directive,
                        query_hint=msg
                    )

        # If explicit mode parameter is "doc" or "document_analysis"
        if mode_param in ("doc", "document_analysis", "doc_intel"):
            return DocTaskConfig(
                task_type="summarize",
                directive=DOC_TASK_RULES[-1][1],
                query_hint=msg
            )

        return None

    def build_doc_system_prompt(
        self,
        config: DocTaskConfig,
        multi_doc_context: Optional[Dict[str, List[str]]] = None,
        single_rag_context: Optional[str] = None
    ) -> str:
        """Build system prompt overlay with multi-document context grounding."""
        ctx_str = ""

        if multi_doc_context:
            doc_blocks = []
            for fname, chunks in multi_doc_context.items():
                content = "\n---\n".join(chunks)
                doc_blocks.append(f"=== DOCUMENT: '{fname}' ===\n{content}\n===============================")
            ctx_str = "\n\n" + "\n\n".join(doc_blocks)
        elif single_rag_context:
            ctx_str = f"\n\n=== RETRIEVED DOCUMENT CONTEXT ===\n{single_rag_context}\n==================================="

        grounding_note = (
            "\nGROUNDING REQUIREMENT: Base your analysis strictly on the provided document context. "
            "Cite document file names (e.g., `[report.pdf]`) for key statements and findings."
        ) if ctx_str else "\nNOTE: No specific document context was retrieved. Request the user to upload relevant documents if needed."

        return (
            f"\n\n=== DOCUMENT INTELLIGENCE ACTIVE [{config.task_type.upper()}] ===\n"
            f"{config.directive}\n"
            f"{grounding_note}"
            f"{ctx_str}\n"
            "============================================================"
        )


# Singleton
doc_intelligence_engine = DocIntelligenceEngine()

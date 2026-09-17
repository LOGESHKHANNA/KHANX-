"""
KHANX Multi-Source Autonomous Research Agent.

For complex, multi-faceted research queries, this agent:
1. Plans Research: Decomposes complex queries into targeted sub-queries.
2. Searches Multiple Sources: Queries both internal ChromaDB RAG documents and external Web Search.
3. Collects & Aggregates Information: Gathers facts, statistics, excerpts, and references.
4. Compares Results: Synthesizes internal document knowledge with live web findings.
5. Generates a Cited Answer: Produces a structured report with explicit inline citations ([Doc: filename], [Web: source]).

Falls back seamlessly to the standard orchestrator chatbot if research is unavailable.
"""

import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from app.agent.tools.registry import tool_registry


@dataclass
class ResearchPlan:
    """Structured Research Plan."""
    original_query: str
    sub_queries_rag: List[str]
    sub_queries_web: List[str]


@dataclass
class ResearchFinding:
    """Individual research finding from RAG or Web."""
    source_type: str  # 'Doc' or 'Web'
    source_name: str  # Filename or URL/Domain
    content: str


class ResearchAgent:
    """Autonomous Research Agent for multi-source planning, gathering, comparison, and cited synthesis."""

    def create_research_plan(self, query: str) -> ResearchPlan:
        """Decompose a complex user query into targeted RAG and Web sub-queries."""
        cleaned = query.strip()

        # Build 2-3 focused search sub-queries
        rag_queries = [
            cleaned,
            f"{cleaned} key facts overview technical details",
        ]

        web_queries = [
            cleaned,
            f"latest updates research overview on {cleaned[:60]}",
        ]

        return ResearchPlan(
            original_query=cleaned,
            sub_queries_rag=rag_queries,
            sub_queries_web=web_queries
        )

    async def execute_research(
        self,
        plan: ResearchPlan,
        user_id: Optional[str] = None,
        db: Optional[Any] = None
    ) -> List[ResearchFinding]:
        """Execute research sub-queries against ChromaDB RAG and Web Search tools."""
        findings: List[ResearchFinding] = []

        # 1. Search Internal ChromaDB RAG Documents
        if user_id:
            try:
                for rq in plan.sub_queries_rag[:2]:
                    rag_result = await tool_registry.execute_tool("search_knowledge_base", {"query": rq}, db=db, user_id=user_id)
                    if rag_result and "No document context" not in rag_result and "No relevant content" not in rag_result:
                        findings.append(ResearchFinding(
                            source_type="Doc",
                            source_name="Uploaded Documents",
                            content=str(rag_result)
                        ))
            except Exception as rag_err:
                print(f"Research Agent RAG search warning: {rag_err}")

        # 2. Search External Web Search
        try:
            for wq in plan.sub_queries_web[:2]:
                web_result = await tool_registry.execute_tool("web_search", {"query": wq})
                if web_result and "Error" not in str(web_result):
                    findings.append(ResearchFinding(
                        source_type="Web",
                        source_name="Web Search Results",
                        content=str(web_result)
                    ))
        except Exception as web_err:
            print(f"Research Agent Web search warning: {web_err}")

        return findings

    def build_research_system_prompt(self, plan: ResearchPlan, findings: List[ResearchFinding]) -> str:
        """Build structured system prompt overlay for generating a cited research synthesis report."""
        rag_findings = [f for f in findings if f.source_type == "Doc"]
        web_findings = [f for f in findings if f.source_type == "Web"]

        findings_text = ""
        if rag_findings:
            findings_text += "\n\n=== INTERNAL DOCUMENT RAG FINDINGS ===\n"
            for f in rag_findings:
                findings_text += f"Source: [{f.source_type}: {f.source_name}]\n{f.content}\n---\n"
            findings_text += "========================================="

        if web_findings:
            findings_text += "\n\n=== EXTERNAL WEB SEARCH FINDINGS ===\n"
            for f in web_findings:
                findings_text += f"Source: [{f.source_type}: {f.source_name}]\n{f.content}\n---\n"
            findings_text += "========================================"


        return (
            "\n\n=== AUTONOMOUS RESEARCH AGENT ACTIVE ===\n"
            "You are conducting a multi-source deep research synthesis.\n"
            "Your objective: Combine internal document knowledge with external web search results into a unified, cited report.\n"
            "\nSTRUCTURE YOUR RESPONSE AS:\n"
            "1. **Research Summary & Core Objective**\n"
            "2. **Synthesized Key Findings** (Use inline citations like `[Doc: filename]` for document context and `[Web: source]` for web search results)\n"
            "3. **Multi-Source Comparison Table** (Aspect/Topic | Internal Document Insights | External Web Insights | Alignment/Divergence)\n"
            "4. **Critical Analysis & Strategic Takeaways**\n"
            "5. **References & Sources**\n"
            "\nCITATION REQUIREMENT: Attribute every major claim to either `[Doc: filename]` or `[Web: source]`.\n"
            f"{findings_text}\n"
            "============================================================"
        )

    def is_research_query(self, query: str, mode_param: str = "chat") -> bool:
        """Detect if user query calls for deep research synthesis."""
        if mode_param in ("research", "deep_research"):
            return True

        research_patterns = [
            r"\b(research|deep\s+dive|thorough\s+study|comprehensive\s+report|literature\s+review)\b",
            r"\b(investigate|gather\s+information|multi-source|synthesize)\b",
            r"\bcompare\s+.*(web|internet|online).*(with|and).*(documents?|files?|pdfs?)\b",
            r"\bsearch\s+.*(web|internet|online).*(and|with).*(documents?|files?|pdfs?)\b",
            r"\b(combine|merge)\s+.*(web|internet|online).*(and|with).*(documents?|files?|pdfs?)\b",
        ]

        for pat in research_patterns:
            if re.search(pat, query, re.IGNORECASE):
                return True

        return False



# Singleton
research_agent = ResearchAgent()

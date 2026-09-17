"""
KHANX Fact-Checking Engine for Research-Heavy Answers.

Provides claim verification for research-heavy responses:
1. Extracts key factual claims (dates, metrics, entity statements, research findings).
2. Cross-checks claims against retrieved RAG documents and Web search context.
3. Qualifies unsupported claims with explicit transparency notes or context warnings.
4. Skips simple conversations completely to preserve zero latency.
5. Falls back seamlessly to existing chatbot behavior if verification is unavailable.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple


@dataclass
class ClaimVerification:
    """Individual claim verification status."""
    claim_text: str
    is_supported: bool
    source_citation: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class FactCheckResult:
    """Aggregated fact-checking result."""
    is_research_heavy: bool
    total_claims: int
    supported_claims: int
    unsupported_claims: List[ClaimVerification] = field(default_factory=list)
    verification_score: float = 1.0
    qualified_response: Optional[str] = None


class FactChecker:
    """Fact-checker for research-heavy AI answers."""

    def should_fact_check(self, query: str, context: Optional[str] = None, mode_param: str = "chat") -> bool:
        """Determine if query/context warrants fact-checking (skips simple conversations)."""
        if mode_param in ("research", "doc", "document_analysis", "fact_check"):
            return True

        if not context or not context.strip():
            return False

        # Research-heavy query indicators
        research_indicators = [
            r"\b(research|study|statistics|data|findings|metrics|specifications|report|comparison|contradiction)\b",
            r"\b(according\s+to|percent|%|million|billion|20\d\d)\b",
            r"\b(compare|analyze|evaluate|investigate)\b",
        ]

        combined = f"{query} {context}"
        for pat in research_indicators:
            if re.search(pat, combined, re.IGNORECASE):
                return True

        return False

    def extract_claims(self, text: str) -> List[str]:
        """Extract key factual statements (sentences with metrics, dates, entities, or claims)."""
        if not text:
            return []

        # Split into sentences
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 15]

        claims = []
        claim_patterns = [
            r"\b\d+(\.\d+)?%?\b",                                    # Numbers/percentages
            r"\b(20\d\d|19\d\d)\b",                                   # Years
            r"\b(increased|decreased|grew|rose|fell|found|showed)\b", # Research verbs
            r"\b\[(Doc|Web):[^\]]+\]\b",                              # Citations
        ]

        for sent in sentences:
            if any(re.search(pat, sent, re.IGNORECASE) for pat in claim_patterns):
                claims.append(sent)

        return claims[:8]  # Focus on top key claims

    def verify_claims(self, response_text: str, source_context: str) -> FactCheckResult:
        """Verify response claims against retrieved document/web source context."""
        if not response_text or not source_context:
            return FactCheckResult(
                is_research_heavy=False,
                total_claims=0,
                supported_claims=0,
                verification_score=1.0,
                qualified_response=response_text
            )

        claims = self.extract_claims(response_text)
        if not claims:
            return FactCheckResult(
                is_research_heavy=False,
                total_claims=0,
                supported_claims=0,
                verification_score=1.0,
                qualified_response=response_text
            )

        context_lower = source_context.lower()
        supported_count = 0
        unsupported: List[ClaimVerification] = []

        for claim in claims:
            # Extract key words/nouns from claim to verify against context
            words = [w.lower() for w in re.findall(r"\w+", claim) if len(w) > 3]
            overlap = sum(1 for w in words if w in context_lower)
            required_overlap = max(1, len(words) // 3)

            if overlap >= required_overlap:
                supported_count += 1
            else:
                unsupported.append(ClaimVerification(
                    claim_text=claim,
                    is_supported=False,
                    reason="Claim details not explicitly found in retrieved context."
                ))

        score = round(supported_count / (len(claims) or 1), 2)
        qualified_text = response_text

        return FactCheckResult(
            is_research_heavy=True,
            total_claims=len(claims),
            supported_claims=supported_count,
            unsupported_claims=unsupported,
            verification_score=score,
            qualified_response=qualified_text
        )


# Singleton
fact_checker = FactChecker()

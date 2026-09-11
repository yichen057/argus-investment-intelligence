from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from investment_agent.research.claims import GeneratedClaim
from investment_agent.research.quality import (
    is_no_evidence_answer,
    looks_incomplete_answer,
)


class EvidenceLike(Protocol):
    evidence_id: int
    display_name: str
    excerpt: str


@dataclass(frozen=True)
class CriticFinding:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class CriticReview:
    status: str
    findings: tuple[CriticFinding, ...]


class EvidenceCritic:
    """Rule-based local critic for V1 evidence-grounding checks."""

    def review_answer(
        self,
        *,
        answer: str,
        sources: tuple[EvidenceLike, ...],
    ) -> CriticReview:
        if not answer.strip():
            return CriticReview(
                status="failed",
                findings=(
                    CriticFinding(
                        code="empty_answer",
                        severity="error",
                        message="The answer is empty.",
                    ),
                ),
            )

        if is_no_evidence_answer(answer):
            return CriticReview(
                status="warning",
                findings=(
                    CriticFinding(
                        code="no_evidence_retrieved",
                        severity="warning",
                        message=(
                            "No local evidence was retrieved, so Argus did not "
                            "produce a source-backed answer."
                        ),
                    ),
                ),
            )

        if not sources:
            return CriticReview(
                status="failed",
                findings=(
                    CriticFinding(
                        code="missing_source",
                        severity="error",
                        message="The answer makes a claim but has no source.",
                    ),
                ),
            )

        if looks_incomplete_answer(answer):
            return CriticReview(
                status="warning",
                findings=(
                    CriticFinding(
                        code="incomplete_answer",
                        severity="warning",
                        message=(
                            "The answer appears truncated or contains an unfinished "
                            "table fragment. Re-run the question before using it or "
                            "generating a report."
                        ),
                    ),
                ),
            )

        answer_terms = _content_terms(answer)
        source_terms = set().union(
            *(_content_terms(source.excerpt) for source in sources)
        )
        overlap = answer_terms & source_terms
        if answer_terms and len(overlap) < min(3, len(answer_terms)):
            return CriticReview(
                status="warning",
                findings=(
                    CriticFinding(
                        code="weak_source_overlap",
                        severity="warning",
                        message=(
                            "Argus could not match enough key terms between the "
                            "answer and the retrieved passage. Treat the answer as "
                            "weakly supported and refine the question or source."
                        ),
                    ),
                ),
            )

        return CriticReview(status="passed", findings=())


def include_claim_verification(
    review: CriticReview,
    claims: tuple[GeneratedClaim, ...],
) -> CriticReview:
    failed = [claim for claim in claims if claim.verification.status != "supported"]
    if not failed:
        return review
    findings = tuple(
        CriticFinding(
            code="claim_citation_not_supported",
            severity="warning",
            message=(
                f"{claim.claim_key} is {claim.verification.status}: "
                f"{', '.join(claim.verification.findings)}."
            ),
        )
        for claim in failed
    )
    status = "failed" if any(
        claim.verification.status == "unsupported" for claim in failed
    ) else "warning"
    if review.status == "failed":
        status = "failed"
    elif review.status == "warning" and status != "failed":
        status = "warning"
    return CriticReview(status=status, findings=(*review.findings, *findings))


_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "are",
    "based",
    "because",
    "been",
    "being",
    "between",
    "could",
    "from",
    "have",
    "into",
    "local",
    "might",
    "more",
    "not",
    "only",
    "question",
    "relevant",
    "source",
    "strongest",
    "that",
    "the",
    "this",
    "when",
    "which",
    "with",
}


def _content_terms(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in _STOPWORDS
    }

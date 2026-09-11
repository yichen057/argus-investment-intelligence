from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol


_CITATION_PATTERN = re.compile(r"\[source:([A-Za-z][A-Za-z0-9_-]*)\]", re.I)
_NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])[+-]?\$?\d+(?:\.\d+)?(?:%|[KMBT])?",
    re.I,
)


class ClaimSource(Protocol):
    evidence_id: int
    display_name: str


@dataclass(frozen=True)
class ClaimEvidence:
    citation_id: str
    text: str
    display_name: str
    evidence_id: int | None = None
    structured_numeric: bool = False


@dataclass(frozen=True)
class ClaimVerification:
    status: str
    findings: tuple[str, ...]
    term_overlap: float


@dataclass(frozen=True)
class GeneratedClaim:
    claim_key: str
    claim_text: str
    citation_ids: tuple[str, ...]
    evidence_ids: tuple[int, ...]
    relations: dict[str, str]
    confidence: float
    source_names: tuple[str, ...]
    verification: ClaimVerification


class ClaimCitationVerifier:
    """Verify each atomic claim only against the passages it cites."""

    def verify(
        self,
        *,
        claim_text: str,
        citation_ids: tuple[str, ...],
        evidence_by_citation: dict[str, ClaimEvidence],
    ) -> ClaimVerification:
        if not citation_ids:
            return ClaimVerification("unsupported", ("missing_citation",), 0.0)
        missing = tuple(
            citation_id
            for citation_id in citation_ids
            if citation_id not in evidence_by_citation
        )
        if missing:
            return ClaimVerification(
                "unsupported",
                tuple(f"unknown_citation:{item}" for item in missing),
                0.0,
            )
        evidence_text = " ".join(
            evidence_by_citation[citation_id].text for citation_id in citation_ids
        )
        claim_numbers = {_canonical_number(item) for item in _NUMBER_PATTERN.findall(claim_text)}
        evidence_numbers = {
            _canonical_number(item) for item in _NUMBER_PATTERN.findall(evidence_text)
        }
        unsupported_numbers = claim_numbers - evidence_numbers
        if unsupported_numbers and any(
            evidence_by_citation[citation_id].structured_numeric
            for citation_id in citation_ids
        ):
            evidence_magnitudes = {
                _canonical_magnitude(item)
                for item in _NUMBER_PATTERN.findall(evidence_text)
            }
            unsupported_numbers = {
                item
                for item in unsupported_numbers
                if _canonical_magnitude(item) not in evidence_magnitudes
            }
        if unsupported_numbers:
            return ClaimVerification(
                "unsupported",
                tuple(
                    f"number_not_in_cited_evidence:{item}"
                    for item in sorted(unsupported_numbers)
                ),
                0.0,
            )
        claim_terms = _content_terms(claim_text)
        evidence_terms = _content_terms(evidence_text)
        overlap_count = len(claim_terms & evidence_terms)
        overlap = overlap_count / max(1, len(claim_terms))
        if not claim_terms or overlap_count == 0:
            return ClaimVerification(
                "unsupported",
                ("no_material_term_overlap",),
                round(overlap, 4),
            )
        if overlap_count < min(2, len(claim_terms)) or overlap < 0.18:
            return ClaimVerification(
                "weak",
                ("limited_term_overlap",),
                round(overlap, 4),
            )
        return ClaimVerification("supported", (), round(overlap, 4))


class ClaimGenerator:
    """Split a grounded answer into atomic claims with stable run-local IDs."""

    def generate(
        self,
        *,
        answer: str,
        sources: tuple[ClaimSource, ...],
        evidence: tuple[ClaimEvidence, ...] | None = None,
    ) -> tuple[GeneratedClaim, ...]:
        if not answer.strip() or _is_no_evidence_answer(answer) or not sources:
            return ()
        evidence_rows = evidence or tuple(
            ClaimEvidence(
                citation_id=f"E{source.evidence_id}",
                text=str(getattr(source, "excerpt", "")),
                display_name=source.display_name,
                evidence_id=source.evidence_id,
                structured_numeric=getattr(source, "source_type", "") == "csv",
            )
            for source in sources
        )
        return generate_structured_claims(answer=answer, evidence=evidence_rows)


def generate_structured_claims(
    *,
    answer: str,
    evidence: tuple[ClaimEvidence, ...],
    require_explicit_citations: bool = False,
) -> tuple[GeneratedClaim, ...]:
    if not answer.strip() or _is_no_evidence_answer(answer) or not evidence:
        return ()
    evidence_by_citation = {item.citation_id: item for item in evidence}
    fallback_ids = tuple(evidence_by_citation)
    verifier = ClaimCitationVerifier()
    claims: list[GeneratedClaim] = []
    for raw_claim in _atomic_claim_texts(answer):
        explicit_ids = tuple(dict.fromkeys(_CITATION_PATTERN.findall(raw_claim)))
        citation_ids = (
            explicit_ids
            if explicit_ids or require_explicit_citations
            else fallback_ids
        )
        claim_text = _CITATION_PATTERN.sub("", raw_claim).strip(" -\t")
        if not _is_material_claim(claim_text):
            continue
        referenced = tuple(
            evidence_by_citation[citation_id]
            for citation_id in citation_ids
            if citation_id in evidence_by_citation
        )
        evidence_ids = tuple(
            item.evidence_id for item in referenced if item.evidence_id is not None
        )
        verification = verifier.verify(
            claim_text=claim_text,
            citation_ids=citation_ids,
            evidence_by_citation=evidence_by_citation,
        )
        confidence = {
            "supported": 0.85,
            "weak": 0.55,
            "unsupported": 0.20,
        }[verification.status]
        claims.append(
            GeneratedClaim(
                claim_key=f"C{len(claims) + 1}",
                claim_text=claim_text,
                citation_ids=citation_ids,
                evidence_ids=evidence_ids,
                relations={
                    str(item.evidence_id) if item.evidence_id is not None else item.citation_id: "supports"
                    for item in referenced
                },
                confidence=confidence,
                source_names=tuple(item.display_name for item in referenced),
                verification=verification,
            )
        )
    return tuple(claims)


def normalize_claim_text(answer: str) -> str:
    text = " ".join(answer.split())
    prefix = "Based on the strongest local source, "
    if text.startswith(prefix):
        text = text.removeprefix(prefix)
    text = _remove_markdown_headings(text)
    text = _remove_truncated_tail(text)
    return _select_claim_sentence(text)


def _atomic_claim_texts(answer: str) -> tuple[str, ...]:
    if "\n" not in answer and not _CITATION_PATTERN.search(answer):
        fallback = normalize_claim_text(answer)
        return (fallback,) if fallback else ()
    normalized = answer.replace("\r", "\n")
    normalized = normalized.removeprefix("Based on the strongest local source, ")
    normalized = _remove_truncated_tail(normalized)
    rows: list[str] = []
    for block in re.split(r"\n+", normalized):
        block = re.sub(r"^#{1,6}\s+", "", block.strip())
        block = re.sub(r"^(?:[-*+]\s+|\d+[.)]\s+)", "", block)
        if not block or _looks_like_heading(block):
            continue
        rows.extend(
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?。！？])\s+", block)
            if sentence.strip()
        )
    if not rows:
        fallback = normalize_claim_text(answer)
        return (fallback,) if fallback else ()
    return tuple(rows[:24])


def _looks_like_heading(text: str) -> bool:
    return (
        len(text.split()) <= 7
        and not re.search(r"[.!?。！？]$", text)
        and not _CITATION_PATTERN.search(text)
    )


def _is_material_claim(text: str) -> bool:
    if len(re.findall(r"[A-Za-z0-9]+", text)) >= 3:
        return True
    return len(re.findall(r"[\u4e00-\u9fff]", text)) >= 10


def _remove_markdown_headings(text: str) -> str:
    if not text.startswith("#"):
        return text.strip()
    parts = text.removeprefix("#").strip().split()
    for index, token in enumerate(parts[1:], start=1):
        if token[:1].islower():
            return " ".join(parts[max(0, index - 1) :]).strip()
    return " ".join(parts).strip()


def _remove_truncated_tail(text: str) -> str:
    if "..." not in text:
        return text
    before_ellipsis = text.split("...", 1)[0].strip()
    sentence_end = max(
        before_ellipsis.rfind("."),
        before_ellipsis.rfind("?"),
        before_ellipsis.rfind("!"),
    )
    if sentence_end >= 0:
        return before_ellipsis[: sentence_end + 1].strip()
    return before_ellipsis


def _select_claim_sentence(text: str) -> str:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if sentence.strip()
    ]
    if not sentences:
        return text
    cue_words = ("because", "reduce", "support", "strengthened", "fell")
    for sentence in sentences:
        lowered = sentence.lower()
        if any(cue_word in lowered for cue_word in cue_words):
            return sentence
    return sentences[0]


def _content_terms(value: str) -> set[str]:
    latin = {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in _STOPWORDS
    }
    chinese_sequences = re.findall(r"[\u4e00-\u9fff]+", value)
    chinese = {
        sequence[index : index + 2]
        for sequence in chinese_sequences
        for index in range(max(0, len(sequence) - 1))
    }
    return latin | chinese


def _canonical_number(value: str) -> str:
    match = re.fullmatch(
        r"(?P<currency>\$?)(?P<number>[+-]?\d+(?:\.\d+)?)(?P<unit>%|[KMBT])?",
        value,
        flags=re.I,
    )
    if match is None:
        return value
    try:
        number = format(Decimal(match.group("number")).normalize(), "f")
    except InvalidOperation:
        return value
    return f"{match.group('currency')}{number}{(match.group('unit') or '').upper()}"


def _canonical_magnitude(value: str) -> str:
    return _canonical_number(value).lstrip("$").rstrip("%KMBT")


_STOPWORDS = {
    "about", "after", "also", "and", "are", "based", "because", "been",
    "being", "could", "from", "have", "into", "local", "more", "not",
    "only", "source", "that", "the", "this", "when", "which", "with",
}


def _is_no_evidence_answer(answer: str) -> bool:
    lowered = answer.lower()
    return (
        "could not find relevant local evidence" in lowered
        or "could not find sufficiently supported evidence" in lowered
    )

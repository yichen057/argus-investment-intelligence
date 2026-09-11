from __future__ import annotations

import re


_NO_EVIDENCE_PHRASE = "could not find relevant local evidence"
_DANGLING_END_PATTERN = re.compile(
    r"\b(and|or|but|because|although|while|with|without|to|of|for|from|by|in|on|at|as)"
    r"[\s,;:.!?-]*$",
    flags=re.IGNORECASE,
)
_LOCAL_PREFIX = "Based on the strongest local source, "


def is_no_evidence_answer(answer: str) -> bool:
    return _NO_EVIDENCE_PHRASE in answer.lower()


def looks_incomplete_answer(answer: str) -> bool:
    collapsed = " ".join(answer.split()).strip()
    if not collapsed:
        return True
    if collapsed.endswith("...") or collapsed.count("|") >= 4:
        return True
    return bool(_DANGLING_END_PATTERN.search(collapsed))


def is_substantive_report_answer(answer: str) -> bool:
    """Return whether an answer has enough complete content for a research brief.

    This intentionally sets a higher bar than an Ask response. A short supported
    extract can still be useful on screen, but Argus should not expand it into a
    multi-section report that merely repeats the same fragment.
    """

    if is_no_evidence_answer(answer) or looks_incomplete_answer(answer):
        return False
    body = " ".join(answer.split()).strip()
    if body.startswith(_LOCAL_PREFIX):
        body = body.removeprefix(_LOCAL_PREFIX).strip()
    if not body:
        return False

    cjk_count = len(re.findall(r"[\u3400-\u9fff]", body))
    if cjk_count >= 24:
        return True

    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'’-]*", body)
    sentence_count = len(re.findall(r"[.!?](?:\s|$)", body))
    return len(words) >= 24 or (sentence_count >= 2 and len(words) >= 18)

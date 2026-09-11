from investment_agent.research.quality import (
    is_substantive_report_answer,
    looks_incomplete_answer,
)


def test_quality_rejects_dangling_answer_and_thin_extract() -> None:
    assert looks_incomplete_answer(
        "Gold prices rallied to record levels in nominal and real terms, and."
    )
    assert not is_substantive_report_answer(
        "Based on the strongest local source, Gold prices reached a record."
    )


def test_quality_accepts_substantive_complete_analysis() -> None:
    assert is_substantive_report_answer(
        "Based on the strongest local source, lower real yields reduce the "
        "opportunity cost of holding gold and can support demand. Higher real "
        "yields can reverse that support by making interest-bearing assets more "
        "attractive relative to a non-yielding asset."
    )

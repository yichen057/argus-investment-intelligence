from __future__ import annotations

from investment_agent.harness.types import ToolResult
from investment_agent.providers import DeterministicMockModelProvider
from investment_agent.providers.types import ModelRequest


def test_mock_provider_cleans_evidence_text_before_answering() -> None:
    response = DeterministicMockModelProvider().generate(
        ModelRequest(
            objective="Why might gold benefit when real yields fall?",
            role="researcher",
            sensitivity="public",
            as_of_date=None,
            iteration=2,
            tool_results=(
                ToolResult(
                    call_id="retrieve-1",
                    status="ok",
                    output={
                        "results": [
                            {
                                "text": (
                                    "# Gold And Real Yields Gold demand strengthened "
                                    "as real yields fell and central banks bought "
                                    "more reserves. Lower real yields can reduce the "
                                    "opportunity cost of holding gold, which may "
                                    "support investment demand when i..."
                                )
                            }
                        ]
                    },
                ),
            ),
        )
    )

    assert response.content == (
        "Based on the strongest local source, Gold demand strengthened as real "
        "yields fell and central banks bought more reserves."
    )


def test_mock_provider_rejects_partial_term_overlap_for_specific_concept() -> None:
    response = DeterministicMockModelProvider().generate(
        ModelRequest(
            objective="Why might gold benefit when real yields fall?",
            role="researcher",
            sensitivity="public",
            as_of_date=None,
            iteration=2,
            tool_results=(
                ToolResult(
                    call_id="retrieve-1",
                    status="ok",
                    output={
                        "results": [
                            {
                                "text": (
                                    "Should the spend on gold rise (fall), gold prices "
                                    "increase (decline), depending on mine supply.\n"
                                    "5\nWhy are gold prices where they are?"
                                )
                            }
                        ]
                    },
                ),
            ),
        )
    )

    assert response.content == "I could not find relevant local evidence for this question."


def test_mock_provider_does_not_append_pdf_question_heading() -> None:
    response = DeterministicMockModelProvider().generate(
        ModelRequest(
            objective="How does spending on gold affect gold prices?",
            role="researcher",
            sensitivity="public",
            as_of_date=None,
            iteration=2,
            tool_results=(
                ToolResult(
                    call_id="retrieve-1",
                    status="ok",
                    output={
                        "results": [
                            {
                                "text": (
                                    "When gross spending on gold rises, gold prices can "
                                    "increase if short-run supply is limited.\n"
                                    "5\nWhy are gold prices where they are?"
                                )
                            }
                        ]
                    },
                ),
            ),
        )
    )

    assert "When gross spending on gold rises" in response.content
    assert "Why are gold prices where they are" not in response.content


def test_mock_provider_reconstructs_wrapped_pdf_sentence_before_answering() -> None:
    response = DeterministicMockModelProvider().generate(
        ModelRequest(
            objective=(
                "What downside risks does the report identify for gold in 2H 2026?"
            ),
            role="researcher",
            sensitivity="public",
            as_of_date=None,
            iteration=2,
            tool_results=(
                ToolResult(
                    call_id="retrieve-1",
                    status="ok",
                    output={
                        "results": [
                            {
                                "text": (
                                    "We remain constructive on gold, but a turn higher in US\n"
                                    "growth sentiment / bottoming in US real interest rates\n"
                                    "into the mid-terms and a lowering of geopolitical risks\n"
                                    "(potential Russia – Ukraine deal) presents major downside\n"
                                    "risks during the 2H’26."
                                )
                            }
                        ]
                    },
                ),
            ),
        )
    )

    assert response.content == (
        "Based on the strongest local source, We remain constructive on gold, but a "
        "turn higher in US growth sentiment / bottoming in US real interest rates into "
        "the mid-terms and a lowering of geopolitical risks (potential Russia – Ukraine "
        "deal) presents major downside risks during the 2H’26."
    )


def test_mock_provider_uses_neighbor_context_to_complete_chunk_boundary() -> None:
    response = DeterministicMockModelProvider().generate(
        ModelRequest(
            objective="How do real yields impact gold prices?",
            role="researcher",
            sensitivity="public",
            as_of_date=None,
            iteration=2,
            tool_results=(
                ToolResult(
                    call_id="retrieve-1",
                    status="ok",
                    output={
                        "results": [
                            {
                                "text": (
                                    "Gold prices have rallied to record levels in nominal "
                                    "and real terms, and"
                                ),
                                "context": (
                                    "Gold prices have rallied to record levels in nominal "
                                    "and real terms, and lower real yields reduce the "
                                    "opportunity cost of holding a non-yielding asset. "
                                    "Higher real yields can reverse that support by making "
                                    "interest-bearing assets relatively more attractive."
                                ),
                            }
                        ]
                    },
                ),
            ),
        )
    )

    assert response.content.endswith(
        "Higher real yields can reverse that support by making interest-bearing "
        "assets relatively more attractive."
    )
    assert not response.content.endswith("and.")


def test_mock_provider_rejects_dangling_chunk_without_neighbor_context() -> None:
    response = DeterministicMockModelProvider().generate(
        ModelRequest(
            objective="How do real yields impact gold prices?",
            role="researcher",
            sensitivity="public",
            as_of_date=None,
            iteration=2,
            tool_results=(
                ToolResult(
                    call_id="retrieve-1",
                    status="ok",
                    output={
                        "results": [
                            {
                                "text": (
                                    "Gold prices have rallied to record levels in nominal "
                                    "and real terms, and"
                                )
                            }
                        ]
                    },
                ),
            ),
        )
    )

    assert response.content == "I could not find relevant local evidence for this question."


def test_mock_provider_rejects_partial_table_row_without_direct_support() -> None:
    response = DeterministicMockModelProvider().generate(
        ModelRequest(
            objective="Why might gold fall in 2026?",
            role="researcher",
            sensitivity="internal",
            as_of_date=None,
            iteration=2,
            tool_results=(
                ToolResult(
                    call_id="retrieve-1",
                    status="ok",
                    output={
                        "results": [
                            {
                                "text": (
                                    "ng debts to China |\n"
                                    "| **Blocking capital markets** | Germany banned "
                                    "purchases |\n"
                                    "| **Wartime controls** | Gold becomes a trusted "
                                    "international currency |"
                                ),
                                "title": "2026 world order notes",
                            }
                        ]
                    },
                ),
            ),
        )
    )

    assert response.content == "I could not find relevant local evidence for this question."


def test_mock_provider_summarizes_csv_evidence_before_answering() -> None:
    response = DeterministicMockModelProvider().generate(
        ModelRequest(
            objective="Summarize the dataset trend.",
            role="researcher",
            sensitivity="public",
            as_of_date=None,
            iteration=2,
            tool_results=(
                ToolResult(
                    call_id="retrieve-1",
                    status="ok",
                    output={
                        "results": [
                            {
                                "source_type": "csv",
                                "text": (
                                    "year,gold_return_pct,real_yield_pct,etf_flows_b,"
                                    "central_bank_demand_share_pct\n"
                                    "2021,-4,-1.1,-9,14\n"
                                    "2022,1,1.6,-3,17\n"
                                    "2023,13,1.8,-1,21\n"
                                    "2024,27,1.5,2,22\n"
                                    "2025,19,0.8,3,23\n"
                                ),
                            }
                        ]
                    },
                ),
            ),
        )
    )

    assert "year,gold_return_pct" not in response.content
    assert "Gold Return rose from -4% in 2021 to 19% in 2025" in response.content
    assert "Real Yield rose from -1.1% in 2021 to 0.8% in 2025" in response.content
    assert "ETF Flows rose from -$9B in 2021 to $3B in 2025" in response.content


def test_mock_provider_focuses_csv_answer_on_query_terms() -> None:
    csv_result = ToolResult(
        call_id="retrieve-1",
        status="ok",
        output={
            "results": [
                {
                    "source_type": "csv",
                    "text": (
                        "year,gold_return_pct,real_yield_pct,etf_flows_b,"
                        "central_bank_demand_share_pct\n"
                        "2021,-4,-1.1,-9,14\n"
                        "2022,1,1.6,-3,17\n"
                        "2023,13,1.8,-1,21\n"
                        "2024,27,1.5,2,22\n"
                        "2025,19,0.8,3,23\n"
                    ),
                }
            ]
        },
    )

    gold_response = DeterministicMockModelProvider().generate(
        ModelRequest(
            objective="What is the gold return trend?",
            role="researcher",
            sensitivity="public",
            as_of_date=None,
            iteration=2,
            tool_results=(csv_result,),
        )
    )
    flows_response = DeterministicMockModelProvider().generate(
        ModelRequest(
            objective="What is the ETF flows trend?",
            role="researcher",
            sensitivity="public",
            as_of_date=None,
            iteration=2,
            tool_results=(csv_result,),
        )
    )

    assert gold_response.content != flows_response.content
    assert "Gold Return rose from -4% in 2021 to 19% in 2025" in gold_response.content
    assert "ETF Flows" not in gold_response.content
    assert "ETF Flows rose from -$9B in 2021 to $3B in 2025" in flows_response.content
    assert "Gold Return" not in flows_response.content


def test_mock_provider_answers_factor_questions_from_factor_columns() -> None:
    response = DeterministicMockModelProvider().generate(
        ModelRequest(
            objective="What's the factor can influence gold price?",
            role="researcher",
            sensitivity="public",
            as_of_date=None,
            iteration=2,
            tool_results=(
                ToolResult(
                    call_id="retrieve-1",
                    status="ok",
                    output={
                        "results": [
                            {
                                "source_type": "csv",
                                "text": (
                                    "year,gold_return_pct,real_yield_pct,etf_flows_b,"
                                    "central_bank_demand_share_pct\n"
                                    "2021,-4,-1.1,-9,14\n"
                                    "2022,1,1.6,-3,17\n"
                                    "2023,13,1.8,-1,21\n"
                                    "2024,27,1.5,2,22\n"
                                    "2025,19,0.8,3,23\n"
                                ),
                            }
                        ]
                    },
                ),
            ),
        )
    )

    assert "possible gold-price factors" in response.content
    assert "Real Yield rose from -1.1% in 2021 to 0.8% in 2025" in response.content
    assert "ETF Flows rose from -$9B in 2021 to $3B in 2025" in response.content
    assert "Central Bank Demand Share rose from 14% in 2021 to 23% in 2025" in response.content
    assert "Gold Return" not in response.content


def test_mock_provider_returns_no_evidence_when_csv_has_no_matching_metric() -> None:
    response = DeterministicMockModelProvider().generate(
        ModelRequest(
            objective="What is the semiconductor margin trend?",
            role="researcher",
            sensitivity="public",
            as_of_date=None,
            iteration=2,
            tool_results=(
                ToolResult(
                    call_id="retrieve-1",
                    status="ok",
                    output={
                        "results": [
                            {
                                "source_type": "csv",
                                "text": (
                                    "year,gold_return_pct,real_yield_pct\n"
                                    "2021,-4,-1.1\n"
                                    "2022,1,1.6\n"
                                    "2023,13,1.8\n"
                                ),
                            }
                        ]
                    },
                ),
            ),
        )
    )

    assert response.content == "I could not find relevant local evidence for this question."


def test_mock_provider_does_not_treat_csv_metric_as_investment_advice() -> None:
    response = DeterministicMockModelProvider().generate(
        ModelRequest(
            objective="Can I invest gold in 2026?",
            role="researcher",
            sensitivity="public",
            as_of_date=None,
            iteration=2,
            tool_results=(
                ToolResult(
                    call_id="retrieve-1",
                    status="ok",
                    output={
                        "results": [
                            {
                                "source_type": "csv",
                                "text": (
                                    "year,gold_return_pct,real_yield_pct\n"
                                    "2021,-4,-1.1\n"
                                    "2022,1,1.6\n"
                                    "2023,13,1.8\n"
                                    "2024,27,1.5\n"
                                    "2025,19,0.8\n"
                                ),
                            }
                        ]
                    },
                ),
            ),
        )
    )

    assert response.content == "I could not find relevant local evidence for this question."


def test_mock_provider_returns_no_evidence_when_csv_does_not_cover_requested_year() -> None:
    response = DeterministicMockModelProvider().generate(
        ModelRequest(
            objective="What's the gold trend in 2027?",
            role="researcher",
            sensitivity="public",
            as_of_date=None,
            iteration=2,
            tool_results=(
                ToolResult(
                    call_id="retrieve-1",
                    status="ok",
                    output={
                        "results": [
                            {
                                "source_type": "csv",
                                "text": (
                                    "year,gold_return_pct,real_yield_pct\n"
                                    "2021,-4,-1.1\n"
                                    "2022,1,1.6\n"
                                    "2023,13,1.8\n"
                                    "2024,27,1.5\n"
                                    "2025,19,0.8\n"
                                ),
                            }
                        ]
                    },
                ),
            ),
        )
    )

    assert response.content == "I could not find relevant local evidence for this question."

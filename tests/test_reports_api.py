from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from investment_agent.app import create_app
from investment_agent.config import Settings
from investment_agent.repositories import AgentRunCreate, AgentRunRepository
from investment_agent.research.reports import _web_answer_sections
from investment_agent.storage import AgentRun, Base, Claim, ModelCall, Report


def test_legacy_web_answer_sections_preserve_abbreviations_and_classify_content() -> (
    None
):
    sections = _web_answer_sections(
        (
            "Real yields proxied by 10-year U.S. TIPS yields often move inversely to gold. "
            "The mechanism has two channels: opportunity cost and safe-haven demand. "
            "A study reported a 13.1% sensitivity. However, the relationship weakened "
            "after 2022 despite higher yields. This decoupling is attributed to central "
            "bank demand. Current evidence suggests structural demand can temporarily "
            "offset rates."
        ),
        question="How do real yields affect gold?",
        grounding_method="test search",
        evidence_scope="web",
    )

    by_heading = {section["heading"]: section["body"] for section in sections}

    assert "U.S. TIPS" in by_heading["Executive Summary"]
    assert "mechanism" in by_heading["Key Claims"]
    assert "13.1%" in by_heading["Supporting Evidence"]
    assert "relationship weakened" in by_heading["Counter-Evidence and Gaps"]
    assert "decoupling is attributed" in by_heading["Counter-Evidence and Gaps"]
    assert "decoupling is attributed" not in by_heading["Key Claims"]
    assert "structural demand" in by_heading["Investment Implications"]


def test_generate_report_persists_json_html_and_claim_links(tmp_path) -> None:
    source = tmp_path / "gold.md"
    source.write_text(
        "Gold demand strengthened as real yields fell and central banks bought "
        "more reserves. Gold return was 19% while central-bank demand share "
        "was 23%. Gold ETF flows were $3B.",
        encoding="utf-8",
    )
    client = client_for_tmp_db(tmp_path)

    ingest_response = client.post("/documents/ingest", json={"path": str(source)})
    chat_response = client.post(
        "/chat/query",
        json={
            "query": "Why might gold benefit when real yields fall?",
            "as_of_date": "2026-01-01",
        },
    )
    generate_response = client.post(
        "/reports/generate",
        json={
            "topic": "Gold Macro",
            "question": "Why might gold benefit when real yields fall?",
            "source_run_id": chat_response.json()["run_id"],
        },
    )

    assert ingest_response.status_code == 201
    assert chat_response.status_code == 200
    assert generate_response.status_code == 201
    payload = generate_response.json()
    assert payload["title"] == "Gold Macro Research Brief"
    assert payload["status"] == "complete"
    assert payload["html_url"] == f"/reports/{payload['report_id']}/html"
    assert payload["report_json"]["schema_version"] == "research-report-v1"
    assert payload["report_json"]["claims"][0]["evidence_ids"]
    assert payload["report_json"]["charts"][0]["title"] == "Cited Percent Indicators"
    assert payload["report_json"]["charts"][0]["data"][0]["display_value"] == "19%"
    assert payload["report_json"]["charts"][1]["title"] == "Cited Currency Indicators"
    assert payload["report_json"]["charts"][1]["data"][0]["display_value"] == "$3B"
    assert {section["heading"] for section in payload["report_json"]["sections"]} >= {
        "Executive Summary",
        "Investment Thesis",
        "Key Claims",
        "Supporting Evidence",
        "Counter-Evidence and Gaps",
        "Risks and Uncertainties",
        "Falsification Conditions",
        "Investment Implications",
        "Critic Review",
    }

    get_response = client.get(f"/reports/{payload['report_id']}")
    html_response = client.get(payload["html_url"])

    assert get_response.status_code == 200
    assert get_response.json()["report_id"] == payload["report_id"]
    assert html_response.status_code == 200
    assert "text/html" in html_response.headers["content-type"]
    assert "Gold Macro Research Brief" in html_response.text
    assert "Data Analysis" in html_response.text
    assert "Cited Percent Indicators" in html_response.text
    assert "Gold return" in html_response.text
    assert "Cited Currency Indicators" in html_response.text
    assert "Counter-Evidence and Gaps" in html_response.text
    assert "Risks and Uncertainties" in html_response.text
    assert "Falsification Conditions" in html_response.text
    assert "Investment Implications" in html_response.text
    assert "Source Ask Cost and Report Cost" in html_response.text
    assert "HTML report generation: 0 provider tokens" in html_response.text
    assert "**" not in html_response.text
    assert "Source: gold.md" in html_response.text
    assert "# Gold" not in html_response.text

    with client.app.state.session_factory() as session:
        report = session.get(Report, payload["report_id"])
        claims = list(
            session.scalars(
                select(Claim).where(Claim.report_id == payload["report_id"])
            )
        )
        model_calls = list(
            session.scalars(
                select(ModelCall).where(ModelCall.run_id == payload["run_id"])
            )
        )
        agent_runs = list(session.scalars(select(AgentRun)))

    assert report is not None
    assert report.rendered_html is not None
    assert len(claims) == 1
    assert claims[0].run_id == payload["run_id"]
    assert len(model_calls) == 2
    assert len(agent_runs) == 1


def test_generate_report_requires_source_run_id(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.post(
        "/reports/generate",
        json={"topic": "ACME Margins", "question": "What is the margin trend?"},
    )

    assert response.status_code == 422
    assert "source-backed Ask run" in response.json()["detail"]


def test_generate_web_report_requires_validated_answer_citation_ids(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)
    with client.app.state.session_factory() as session:
        run = AgentRunRepository(session).create_run(
            AgentRunCreate(
                run_key="web-citation-gate-test",
                role="research",
                objective="How do real yields affect gold?",
                status="complete",
                sensitivity="public",
                as_of_date=None,
                selection_mode="manual",
                selected_model="deepseek/deepseek-v4-flash",
                metadata={
                    "answer": (
                        "## Direct answer\nLower real yields can reduce the opportunity "
                        "cost of holding gold.\n## Supporting evidence\nThe accepted "
                        "source describes the mechanism in complete sentences.\n"
                        "## Risks and uncertainties\nThe relationship can weaken."
                    ),
                    "web_sources": [
                        {
                            "citation_id": "W1",
                            "evidence_key": "web-test",
                            "title": "Real yields and gold",
                            "url": "https://example.com/gold",
                            "retrieved_at": "2026-07-16T00:00:00Z",
                            "excerpt": "Lower real yields reduce opportunity cost.",
                        }
                    ],
                    "citation_status": "missing",
                    "evidence_scope": "web",
                    "search": {
                        "evidence_gate": {
                            "decision": "supported",
                            "report_eligible": True,
                        }
                    },
                },
            )
        )
        session.commit()
        run_id = run.id

    response = client.post(
        "/reports/generate",
        json={
            "topic": "Gold and real yields",
            "question": "How do real yields affect gold?",
            "source_run_id": run_id,
        },
    )

    assert response.status_code == 422
    assert "valid Argus citation IDs" in response.json()["detail"]


def test_generate_report_rejects_incomplete_stored_answer(tmp_path) -> None:
    source = tmp_path / "gold.md"
    source.write_text(
        "Lower real yields reduce the opportunity cost of holding gold and can "
        "support investment demand. Higher real yields can reverse that support.",
        encoding="utf-8",
    )
    client = client_for_tmp_db(tmp_path)
    client.post("/documents/ingest", json={"path": str(source)})
    chat_response = client.post(
        "/chat/query",
        json={"query": "How do real yields affect gold prices?"},
    )

    with client.app.state.session_factory() as session:
        run = session.get(AgentRun, chat_response.json()["run_id"])
        assert run is not None
        run.metadata_json = {
            **(run.metadata_json or {}),
            "answer": (
                "Based on the strongest local source, Gold prices have rallied "
                "to record levels in nominal and real terms, and."
            ),
        }
        session.commit()

    response = client.post(
        "/reports/generate",
        json={
            "topic": "Gold and real yields",
            "question": "How do real yields affect gold prices?",
            "source_run_id": chat_response.json()["run_id"],
        },
    )

    assert response.status_code == 422
    assert "weak or unverified evidence" in response.json()["detail"]


def test_generate_report_uses_selected_document_context(tmp_path) -> None:
    source = tmp_path / "gold_outlook_zh.md"
    source.write_text(
        "黄金展望指出，2026 年金价可能受到央行购金、实际利率变化和投资需求影响。",
        encoding="utf-8",
    )
    client = client_for_tmp_db(tmp_path)

    ingest_response = client.post("/documents/ingest", json={"path": str(source)})
    chat_response = client.post(
        "/chat/query",
        json={
            "query": "Can I invest gold in 2026?",
            "document_id": ingest_response.json()["document_id"],
        },
    )
    generate_response = client.post(
        "/reports/generate",
        json={
            "topic": "Gold Outlook",
            "question": "Can I invest gold in 2026?",
            "source_run_id": chat_response.json()["run_id"],
        },
    )

    assert ingest_response.status_code == 201
    assert chat_response.status_code == 200
    assert generate_response.status_code == 201
    payload = generate_response.json()
    assert payload["status"] == "complete"
    assert payload["report_json"]["claims"]
    assert payload["report_json"]["evidence"][0]["source_name"] == "gold_outlook_zh.md"


def test_generate_report_rejects_when_selected_csv_has_no_matching_metric(
    tmp_path,
) -> None:
    source = tmp_path / "gold_macro_indicators.csv"
    source.write_text(
        "\n".join(
            [
                "year,gold_return_pct,real_yield_pct",
                "2021,-4,-1.1",
                "2022,1,1.6",
                "2023,13,1.8",
            ]
        ),
        encoding="utf-8",
    )
    client = client_for_tmp_db(tmp_path)

    ingest_response = client.post("/documents/ingest", json={"path": str(source)})
    chat_response = client.post(
        "/chat/query",
        json={
            "query": "What is the semiconductor margin trend?",
            "document_id": ingest_response.json()["document_id"],
        },
    )
    generate_response = client.post(
        "/reports/generate",
        json={
            "topic": "Semiconductor Margin",
            "question": "What is the semiconductor margin trend?",
            "source_run_id": chat_response.json()["run_id"],
        },
    )

    assert ingest_response.status_code == 201
    assert chat_response.status_code == 200
    assert generate_response.status_code == 422
    assert (
        "Cannot generate a report without local evidence"
        in generate_response.json()["detail"]
    )


def test_generate_report_renders_structured_csv_trend_charts(tmp_path) -> None:
    source = tmp_path / "gold_macro_indicators.csv"
    source.write_text(
        "\n".join(
            [
                "year,gold_return_pct,real_yield_pct,etf_flows_b,"
                "central_bank_demand_share_pct",
                "2021,-4,-1.1,-9,14",
                "2022,1,1.6,-3,17",
                "2023,13,1.8,-1,21",
                "2024,27,1.5,2,22",
                "2025,19,0.8,3,23",
            ]
        ),
        encoding="utf-8",
    )
    client = client_for_tmp_db(tmp_path)

    ingest_response = client.post("/documents/ingest", json={"path": str(source)})
    chat_response = client.post(
        "/chat/query",
        json={
            "query": (
                "How did gold return real yield ETF flows and central bank "
                "demand trend?"
            ),
            "as_of_date": "2026-01-01",
            "document_id": ingest_response.json()["document_id"],
        },
    )
    generate_response = client.post(
        "/reports/generate",
        json={
            "topic": "Gold Macro Dataset",
            "question": (
                "How did gold return real yield ETF flows and central bank "
                "demand trend?"
            ),
            "source_run_id": chat_response.json()["run_id"],
        },
    )

    assert ingest_response.status_code == 201
    assert chat_response.status_code == 200
    assert generate_response.status_code == 201
    payload = generate_response.json()
    assert payload["report_json"]["answer"].startswith(
        "Based on the strongest local source, Gold Return rose"
    )
    assert "year,gold_return_pct" not in payload["report_json"]["answer"]
    charts = payload["report_json"]["charts"]
    chart_types = {chart["chart_type"] for chart in charts}
    percent_chart = next(chart for chart in charts if chart["chart_type"] == "line")
    flows_chart = next(chart for chart in charts if chart["chart_type"] == "time_bar")

    assert chart_types >= {"line", "time_bar"}
    assert percent_chart["title"] == "Percent Trend: gold_macro_indicators.csv"
    assert (
        "Gold Return rose from -4% in 2021 to 19% in 2025" in percent_chart["narrative"]
    )
    assert percent_chart["series"][0]["label"] == "Gold Return"
    assert percent_chart["series"][0]["values"][-1]["display_value"] == "19%"
    assert flows_chart["title"] == "ETF Flows Trend"
    assert "ETF Flows rose from -$9B in 2021 to $3B in 2025" in flows_chart["narrative"]
    assert flows_chart["series"][0]["values"][0]["display_value"] == "-$9B"
    assert any(
        section["heading"] == "Data Interpretation"
        and "Percent Trend: gold_macro_indicators.csv" in section["body"]
        for section in payload["report_json"]["sections"]
    )

    html_response = client.get(payload["html_url"])

    assert html_response.status_code == 200
    assert "Data Interpretation" in html_response.text
    assert "What it shows:" in html_response.text
    assert "Percent Trend: gold_macro_indicators.csv" in html_response.text
    assert "ETF Flows Trend" in html_response.text
    assert "<polyline" in html_response.text
    assert "<rect" in html_response.text


def test_generate_report_focuses_csv_charts_on_question_metric(tmp_path) -> None:
    source = tmp_path / "gold_macro_indicators.csv"
    source.write_text(
        "\n".join(
            [
                "year,gold_return_pct,real_yield_pct,etf_flows_b,"
                "central_bank_demand_share_pct",
                "2021,-4,-1.1,-9,14",
                "2022,1,1.6,-3,17",
                "2023,13,1.8,-1,21",
                "2024,27,1.5,2,22",
                "2025,19,0.8,3,23",
            ]
        ),
        encoding="utf-8",
    )
    client = client_for_tmp_db(tmp_path)

    ingest_response = client.post("/documents/ingest", json={"path": str(source)})
    chat_response = client.post(
        "/chat/query",
        json={
            "query": "What is the gold return trend?",
            "document_id": ingest_response.json()["document_id"],
        },
    )
    generate_response = client.post(
        "/reports/generate",
        json={
            "topic": "Gold Return Trend",
            "question": "What is the gold return trend?",
            "source_run_id": chat_response.json()["run_id"],
        },
    )

    assert ingest_response.status_code == 201
    assert chat_response.status_code == 200
    assert generate_response.status_code == 201
    payload = generate_response.json()
    charts = payload["report_json"]["charts"]

    assert len(charts) == 1
    assert charts[0]["chart_type"] == "line"
    assert [series["label"] for series in charts[0]["series"]] == ["Gold Return"]
    assert "Gold Return rose from -4% in 2021 to 19% in 2025" in charts[0]["narrative"]
    assert "ETF Flows" not in payload["report_json"]["sections"][2]["body"]


def test_generate_report_cleans_question_prefix_from_title(tmp_path) -> None:
    source = tmp_path / "gold_macro_indicators.csv"
    source.write_text(
        "\n".join(
            [
                "year,gold_return_pct,real_yield_pct",
                "2021,-4,-1.1",
                "2022,1,1.6",
                "2023,13,1.8",
                "2024,27,1.5",
                "2025,19,0.8",
            ]
        ),
        encoding="utf-8",
    )
    client = client_for_tmp_db(tmp_path)

    ingest_response = client.post("/documents/ingest", json={"path": str(source)})
    chat_response = client.post(
        "/chat/query",
        json={
            "query": "What is the gold asset value trend?",
            "document_id": ingest_response.json()["document_id"],
        },
    )
    generate_response = client.post(
        "/reports/generate",
        json={
            "topic": "Is The Gold Asset Value Trend",
            "question": "What is the gold asset value trend?",
            "source_run_id": chat_response.json()["run_id"],
        },
    )

    assert ingest_response.status_code == 201
    assert chat_response.status_code == 200
    assert generate_response.status_code == 201
    payload = generate_response.json()
    assert payload["title"] == "Gold Asset Value Trend Research Brief"
    assert payload["report_json"]["topic"] == "Gold Asset Value Trend"


def test_get_report_returns_404_for_missing_report(tmp_path) -> None:
    client = client_for_tmp_db(tmp_path)

    response = client.get("/reports/404")

    assert response.status_code == 404


def client_for_tmp_db(tmp_path) -> TestClient:
    settings = Settings(
        env="test",
        api_host="127.0.0.1",
        api_port=8000,
        api_reload=False,
        cors_origins=("http://localhost:5173",),
        database_url=f"sqlite:///{tmp_path / 'reports_api.db'}",
        enable_cloud_services=False,
        enable_gmail=False,
        enable_robinhood=False,
        default_model_selection_mode="auto",
        self_hosted_model_base_url=None,
        self_hosted_model_name=None,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)

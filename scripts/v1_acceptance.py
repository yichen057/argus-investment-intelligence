from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from investment_agent.app import create_app
from investment_agent.config import get_settings
from investment_agent.storage import ChunkEmbedding


RESEARCH = """# Gold And Real Yields

Gold demand strengthened as real yields fell and central banks bought more
reserves. Lower real yields can reduce the opportunity cost of holding gold,
which may support investment demand when investors expect monetary easing.

Gold return was 19% while central-bank demand share was 23%. Gold ETF flows
were $3B after a prior year of outflows.
"""

HOLDINGS = """symbol,name,asset_class,quantity,price,market_value,cost_basis,account
AAPL,Apple Inc,Equity,10,200,2000,1500,Taxable
BND,Vanguard Total Bond Market ETF,Bond,20,50,1000,950,IRA
CASH,Cash Sweep,Cash,1,500,500,500,Taxable
"""

REQUIRED_REPORT_SECTIONS = {
    "Executive Summary",
    "Investment Thesis",
    "Supporting Evidence",
    "Counter-Evidence and Gaps",
    "Risks and Uncertainties",
    "Falsification Conditions",
    "Investment Implications",
    "Critic Review",
}


def main() -> None:
    settings = get_settings()
    if "acceptance" not in settings.database_url:
        raise RuntimeError("Acceptance must run against an isolated database.")

    app = create_app(settings)
    client = TestClient(app)

    health = _ok(client.get("/health"))
    ingest = _ok(
        client.post(
            "/documents/upload",
            content=RESEARCH.encode("utf-8"),
            headers={
                "Content-Type": "application/octet-stream",
                "X-Argus-Filename": "gold_real_yields.md",
            },
        ),
        expected=201,
    )
    document_id = ingest["document_id"]

    answer = _ok(
        client.post(
            "/chat/query",
            json={
                "query": "What factors can influence gold prices?",
                "document_id": document_id,
                "sensitivity": "public",
            },
        )
    )
    assert answer["evidence_ids"]
    assert answer["sources"]

    unrelated = _ok(
        client.post(
            "/chat/query",
            json={
                "query": "What affects semiconductor margins?",
                "document_id": document_id,
                "sensitivity": "public",
            },
        )
    )
    assert unrelated["evidence_ids"] == []

    future = _ok(
        client.post(
            "/chat/query",
            json={
                "query": "What is the gold trend in 2027?",
                "document_id": document_id,
                "sensitivity": "public",
            },
        )
    )
    assert future["evidence_ids"] == []

    report = _ok(
        client.post(
            "/reports/generate",
            json={
                "topic": "Gold Price Drivers",
                "question": "What factors can influence gold prices?",
                "source_run_id": answer["run_id"],
            },
        ),
        expected=201,
    )
    headings = {
        section["heading"] for section in report["report_json"]["sections"]
    }
    assert REQUIRED_REPORT_SECTIONS <= headings

    profile = _ok(
        client.post(
            "/profile",
            json={
                "risk_tolerance": "moderate",
                "life_stage": "early_career_single",
                "investment_horizon": "long_term",
                "income_stability": "stable",
                "liquidity_needs": "medium",
                "preferred_style": "broad_index_passive",
                "target_allocation": {"Equity": 0.6, "Bond": 0.3, "Cash": 0.1},
            },
        ),
        expected=201,
    )

    holdings_path = Path("/tmp/argus_v1_acceptance_holdings.csv")
    holdings_path.write_text(HOLDINGS, encoding="utf-8")
    portfolio = _ok(
        client.post("/portfolio/upload", json={"path": str(holdings_path)}),
        expected=201,
    )
    runs = _ok(client.get("/runs"))

    with app.state.session_factory() as session:
        semantic_embeddings = list(
            session.scalars(
                select(ChunkEmbedding).where(
                    ChunkEmbedding.provider == "google",
                    ChunkEmbedding.model == settings.gemini_embedding_model,
                    ChunkEmbedding.dimensions == settings.gemini_embedding_dimensions,
                    ChunkEmbedding.embedding_vector.is_not(None),
                )
            )
        )
    assert semantic_embeddings

    print(
        json.dumps(
            {
                "health": health["status"],
                "document_id": document_id,
                "semantic_embedding_rows": len(semantic_embeddings),
                "answer_run_id": answer["run_id"],
                "answer_has_citations": bool(answer["evidence_ids"]),
                "unrelated_query_refused": unrelated["evidence_ids"] == [],
                "future_query_refused": future["evidence_ids"] == [],
                "report_id": report["report_id"],
                "report_sections": sorted(headings),
                "profile_id": profile["id"],
                "portfolio_total_value": portfolio["summary"]["total_value"],
                "run_count": runs["total_runs"],
                "paid_tier_equivalent_usd": answer[
                    "total_estimated_cost_usd"
                ],
            },
            indent=2,
        )
    )


def _ok(response, *, expected: int = 200):
    if response.status_code != expected:
        raise RuntimeError(
            f"HTTP {response.status_code}, expected {expected}: {response.text}"
        )
    return response.json()


if __name__ == "__main__":
    main()

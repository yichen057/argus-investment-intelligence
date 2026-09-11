# Supply-chain bottleneck research Method Pack

The prose in this file is documentation for the user. Argus reads only the fenced
`argus-method-pack` JSON object below; it never executes Markdown instructions, shell
commands, Python, or linked files.

```argus-method-pack
{
  "schema_version": 1,
  "id": "supply_chain_bottleneck",
  "name": "Supply-chain bottleneck research",
  "description": "Tests an investment thesis by locating constrained industry-chain nodes, validating pricing power, and requiring counter-evidence.",
  "research_lenses": [
    "fundamentals",
    "quality",
    "downside_risk",
    "counter_evidence"
  ],
  "portfolio_priorities": [
    "broad_diversification",
    "quality_tilt"
  ],
  "product_preferences": [
    "broad_market_etf",
    "individual_stock_satellite"
  ],
  "report_section_order": [
    "executive_summary",
    "thesis",
    "drivers",
    "quality",
    "risks",
    "counter_evidence",
    "falsification",
    "portfolio_implications",
    "next_checks"
  ],
  "allocation_policy": {
    "equity_adjustment_points": 0,
    "international_share_of_equity": 0.2,
    "gold_adjustment_points": 0,
    "alternatives_points": 0
  },
  "references": [],
  "required_evidence_slots": [
    {
      "id": "industry_bottleneck",
      "description": "Evidence that identifies the constrained node, its cause, and the duration of the constraint.",
      "search_terms": ["bottleneck", "capacity", "constraint", "shortage"],
      "query_template": "industry chain bottleneck capacity constraint {question}",
      "minimum_items": 1,
      "minimum_distinct_sources": 1,
      "freshness_days": null,
      "required": true
    },
    {
      "id": "pricing_power",
      "description": "Evidence that connects the bottleneck to price, margin, contract, or revenue effects.",
      "search_terms": ["margin", "price", "pricing", "revenue"],
      "query_template": "pricing power margins revenue evidence {question}",
      "minimum_items": 1,
      "minimum_distinct_sources": 1,
      "freshness_days": null,
      "required": true
    }
  ]
}
```

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Sequence


# Captured from authenticated, metadata-only `list_tools` refreshes, most
# recently on 2026-07-28.
# This list is an audit baseline, not a business-code allowlist.
ROBINHOOD_OBSERVED_TOOL_NAMES = frozenset(
    {
        "add_option_to_watchlist",
        "add_to_watchlist",
        "cancel_equity_order",
        "cancel_option_exercise",
        "cancel_option_order",
        "create_scan",
        "create_watchlist",
        "follow_watchlist",
        "get_accounts",
        "get_earnings_calendar",
        "get_earnings_results",
        "get_equity_fundamentals",
        "get_equity_historicals",
        "get_equity_orders",
        "get_equity_positions",
        "get_equity_price_book",
        "get_equity_quotes",
        "get_equity_tax_lots",
        "get_equity_technical_indicators",
        "get_equity_tradability",
        "get_financials",
        "get_index_quotes",
        "get_indexes",
        "get_option_chains",
        "get_option_historicals",
        "get_option_instruments",
        "get_option_level_upgrade_info",
        "get_option_orders",
        "get_option_positions",
        "get_option_quotes",
        "get_option_watchlist",
        "get_pnl_trade_history",
        "get_popular_watchlists",
        "get_portfolio",
        "get_realized_pnl",
        "get_scanner_filter_specs",
        "get_scans",
        "get_watchlist_items",
        "get_watchlists",
        "exercise_option",
        "place_equity_order",
        "place_option_order",
        "remove_from_watchlist",
        "remove_option_from_watchlist",
        "review_equity_order",
        "review_option_order",
        "run_scan",
        "search",
        "unfollow_watchlist",
        "update_scan_config",
        "update_scan_filters",
        "update_watchlist",
    }
)

# Phase one permits account discovery only as an internal prerequisite for the
# provider's required ``account_number`` position argument. The account number
# never leaves the Sidecar. Orders, tax lots, watchlists, options, scans,
# technical indicators, and every write-capable tool remain excluded.
# Historicals can be discovered and fingerprinted now but must be explicitly
# enabled after review.
ROBINHOOD_PHASE_ONE_TOOLS = frozenset(
    {
        "get_accounts",
        "get_equity_positions",
        "get_equity_quotes",
    }
)
ROBINHOOD_PENDING_REVIEW_TOOLS = frozenset({"get_equity_historicals"})


@dataclass(frozen=True)
class ToolDeclaration:
    name: str
    description: str
    input_schema: Mapping[str, object]

    @property
    def schema_fingerprint(self) -> str:
        canonical = json.dumps(
            self.input_schema,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CapabilityAudit:
    directory_fingerprint: str
    manifest_fingerprint: str
    observed_count: int
    expected_count: int
    added_tools: tuple[str, ...]
    missing_tools: tuple[str, ...]
    phase_one_schema_fingerprints: Mapping[str, str]
    pending_review_schema_fingerprints: Mapping[str, str]
    ready_for_phase_one_reads: bool


def audit_tool_declarations(
    declarations: Sequence[ToolDeclaration],
) -> CapabilityAudit:
    """Compare live list_tools metadata with the reviewed directory baseline.

    This function never calls a provider tool. A changed directory is fail-closed:
    the operator must review the new tool inventory before data reads are enabled.
    """

    by_name = {declaration.name: declaration for declaration in declarations}
    observed_names = frozenset(by_name)
    added = tuple(sorted(observed_names - ROBINHOOD_OBSERVED_TOOL_NAMES))
    missing = tuple(sorted(ROBINHOOD_OBSERVED_TOOL_NAMES - observed_names))
    directory_fingerprint = hashlib.sha256(
        "\n".join(sorted(observed_names)).encode("utf-8")
    ).hexdigest()
    manifest_fingerprint = hashlib.sha256(
        "\n".join(
            f"{name}:{by_name[name].schema_fingerprint}"
            for name in sorted(observed_names)
        ).encode("utf-8")
    ).hexdigest()
    phase_one = {
        name: by_name[name].schema_fingerprint
        for name in sorted(ROBINHOOD_PHASE_ONE_TOOLS)
        if name in by_name
    }
    pending = {
        name: by_name[name].schema_fingerprint
        for name in sorted(ROBINHOOD_PENDING_REVIEW_TOOLS)
        if name in by_name
    }
    ready = (
        not added
        and not missing
        and set(phase_one) == set(ROBINHOOD_PHASE_ONE_TOOLS)
    )
    return CapabilityAudit(
        directory_fingerprint=directory_fingerprint,
        manifest_fingerprint=manifest_fingerprint,
        observed_count=len(observed_names),
        expected_count=len(ROBINHOOD_OBSERVED_TOOL_NAMES),
        added_tools=added,
        missing_tools=missing,
        phase_one_schema_fingerprints=phase_one,
        pending_review_schema_fingerprints=pending,
        ready_for_phase_one_reads=ready,
    )

---
name: gold-macro
version: 0.1.0
description: Assess the gold regime using real yields, central-bank demand, ETF flows, and COT positioning.
---

# Core Signals

1. Real interest rates: level, direction, tenor, and timestamp.
2. Central-bank purchases: latest flow, trend, lag, and revisions.
3. Gold ETF flows: direction and persistence.
4. CFTC COT positioning: managed-money net position and historical percentile.

# Procedure

1. Fix `as_of_date`.
2. Retrieve each signal with source and timestamp.
3. Normalize units and publication lags.
4. Classify the regime without making a portfolio allocation.
5. Retrieve contradictory evidence.
6. Define invalidation conditions.
7. Use the deterministic portfolio engine before discussing sizing.

# Output

- regime classification;
- signal table;
- data freshness;
- bull/base/bear paths;
- counter-evidence;
- invalidation conditions;
- next releases to monitor.


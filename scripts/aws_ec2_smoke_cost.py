#!/usr/bin/env python3
"""Produce a deterministic, current AWS EC2 smoke cost estimate."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_UP
from typing import Iterable

HOURS_PER_MONTH = Decimal("730")
PUBLIC_IPV4_USD_PER_HOUR = Decimal("0.005")
ECR_USD_PER_GB_MONTH = Decimal("0.10")
FIXED_UNKNOWN_USAGE_RESERVE_USD = Decimal("0.25")


@dataclass(frozen=True)
class CostEstimate:
    hours: Decimal
    ec2: Decimal
    public_ipv4: Decimal
    ebs: Decimal
    ecr: Decimal

    @property
    def base_total(self) -> Decimal:
        return self.ec2 + self.public_ipv4 + self.ebs + self.ecr

    @property
    def guarded_total(self) -> Decimal:
        return self.base_total * Decimal("2") + FIXED_UNKNOWN_USAGE_RESERVE_USD


def _aws_pricing_products(
    profile: str,
    service_code: str,
    filters: Iterable[tuple[str, str]],
) -> list[dict[str, object]]:
    command = [
        "aws",
        "pricing",
        "get-products",
        "--profile",
        profile,
        "--region",
        "us-east-1",
        "--service-code",
        service_code,
        "--filters",
    ]
    for field, value in filters:
        command.append(f"Type=TERM_MATCH,Field={field},Value={value}")
    command.extend(["--max-results", "100", "--output", "json"])
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    return [json.loads(raw) for raw in payload["PriceList"]]


def _single_usd_dimension(
    products: Iterable[dict[str, object]], expected_unit: str
) -> Decimal:
    prices: set[Decimal] = set()
    for product in products:
        terms = product["terms"]
        assert isinstance(terms, dict)
        on_demand = terms["OnDemand"]
        assert isinstance(on_demand, dict)
        for term in on_demand.values():
            assert isinstance(term, dict)
            dimensions = term["priceDimensions"]
            assert isinstance(dimensions, dict)
            for dimension in dimensions.values():
                assert isinstance(dimension, dict)
                if dimension["unit"] == expected_unit:
                    price_per_unit = dimension["pricePerUnit"]
                    assert isinstance(price_per_unit, dict)
                    if "USD" in price_per_unit:
                        prices.add(Decimal(str(price_per_unit["USD"])))
    if len(prices) != 1:
        raise RuntimeError(
            f"Expected one {expected_unit} USD price, received {sorted(prices)}"
        )
    return prices.pop()


def current_unit_prices(profile: str) -> tuple[Decimal, Decimal]:
    ec2_products = _aws_pricing_products(
        profile,
        "AmazonEC2",
        (
            ("location", "US West (Oregon)"),
            ("instanceType", "m7i-flex.large"),
            ("operatingSystem", "Linux"),
            ("tenancy", "Shared"),
            ("preInstalledSw", "NA"),
            ("capacitystatus", "Used"),
        ),
    )
    ebs_products = _aws_pricing_products(
        profile,
        "AmazonEC2",
        (
            ("location", "US West (Oregon)"),
            ("productFamily", "Storage"),
            ("volumeApiName", "gp3"),
        ),
    )
    return (
        _single_usd_dimension(ec2_products, "Hrs"),
        _single_usd_dimension(ebs_products, "GB-Mo"),
    )


def estimate_cost(
    *,
    hours: Decimal,
    root_volume_gib: Decimal,
    ecr_storage_gib: Decimal,
    ec2_hourly: Decimal,
    ebs_gib_month: Decimal,
) -> CostEstimate:
    return CostEstimate(
        hours=hours,
        ec2=ec2_hourly * hours,
        public_ipv4=PUBLIC_IPV4_USD_PER_HOUR * hours,
        ebs=ebs_gib_month * root_volume_gib * hours / HOURS_PER_MONTH,
        ecr=ECR_USD_PER_GB_MONTH * ecr_storage_gib * hours / HOURS_PER_MONTH,
    )


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_UP))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Estimate Argus's temporary us-west-2 EC2 smoke cost."
    )
    parser.add_argument("--profile", default="argus-login")
    parser.add_argument("--hours", type=Decimal, default=Decimal("5"))
    parser.add_argument("--root-volume-gib", type=Decimal, default=Decimal("20"))
    parser.add_argument("--ecr-storage-gib", type=Decimal, default=Decimal("2"))
    args = parser.parse_args()

    if args.hours <= 0 or args.hours > 6:
        parser.error("--hours must be greater than 0 and no more than 6")

    ec2_hourly, ebs_gib_month = current_unit_prices(args.profile)
    estimate = estimate_cost(
        hours=args.hours,
        root_volume_gib=args.root_volume_gib,
        ecr_storage_gib=args.ecr_storage_gib,
        ec2_hourly=ec2_hourly,
        ebs_gib_month=ebs_gib_month,
    )

    print(f"Price check date: {date.today().isoformat()}")
    print("Region / shape: us-west-2 / one m7i-flex.large")
    print(f"Runtime: {args.hours} hours")
    print(f"EC2 compute: ${_money(estimate.ec2)}")
    print(f"One public IPv4: ${_money(estimate.public_ipv4)}")
    print(f"{args.root_volume_gib} GiB gp3 prorated: ${_money(estimate.ebs)}")
    print(f"{args.ecr_storage_gib} GiB ECR prorated: ${_money(estimate.ecr)}")
    print(f"Base estimate: ${_money(estimate.base_total)}")
    print(
        "Guarded estimate (2x base + $0.25 unknown-usage reserve): "
        f"${_money(estimate.guarded_total)}"
    )
    print(
        "Not a bill guarantee: taxes, delayed metering, unexpected data transfer, "
        "or resources outside this Terraform stack are not included."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

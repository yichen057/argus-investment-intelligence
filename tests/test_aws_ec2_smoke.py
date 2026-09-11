from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from scripts.aws_ec2_smoke import (
    ACCOUNT_ID_PATTERN,
    APPLY_CONFIRMATION,
    COMPOSE_FILE,
    DESTROY_CONFIRMATION,
)
from scripts.aws_ec2_smoke_cost import estimate_cost

ROOT = Path(__file__).resolve().parents[1]
TF_DIR = ROOT / "infra" / "terraform" / "aws-ec2-smoke"


def test_cost_estimate_uses_decimal_and_expected_guard() -> None:
    estimate = estimate_cost(
        hours=Decimal("5"),
        root_volume_gib=Decimal("20"),
        ecr_storage_gib=Decimal("2"),
        ec2_hourly=Decimal("0.09576"),
        ebs_gib_month=Decimal("0.08"),
    )

    assert estimate.ec2 == Decimal("0.47880")
    assert estimate.public_ipv4 == Decimal("0.025")
    assert estimate.base_total > Decimal("0.51")
    assert estimate.guarded_total > Decimal("1.27")


def test_operator_confirmations_are_specific() -> None:
    assert APPLY_CONFIRMATION == "CREATE-ARGUS-EC2-SMOKE"
    assert DESTROY_CONFIRMATION == "DESTROY-ARGUS-EC2-SMOKE"
    assert ACCOUNT_ID_PATTERN.sub("<redacted>", "account 123456789012") == (
        "account <redacted>"
    )


def test_cloud_compose_has_no_host_exposure_except_loopback_frontend() -> None:
    compose = COMPOSE_FILE.read_text()

    assert '127.0.0.1:8080:8080' in compose
    assert '"5432:5432"' not in compose
    assert '"6379:6379"' not in compose
    assert '"29092:29092"' not in compose
    assert "ARGUS_ENABLE_CLOUD_SERVICES: \"false\"" in compose
    assert "replication-factor" in compose
    operator = (ROOT / "scripts" / "aws_ec2_smoke.py").read_text()
    assert "--bootstrap kafka:9092 --api-base http://localhost:8000" in operator


def test_ec2_stack_enforces_core_safety_controls() -> None:
    terraform = "\n".join(path.read_text() for path in TF_DIR.glob("*.tf"))

    assert 'http_tokens                 = "required"' in terraform
    assert "http_put_response_hop_limit = 2" in terraform
    assert "encrypted             = true" in terraform
    assert "delete_on_termination = true" in terraform
    assert 'image_tag_mutability = "IMMUTABLE"' in terraform
    assert "AmazonSSMManagedInstanceCore" in terraform
    assert "aws_vpc_security_group_ingress_rule" not in terraform
    assert "aws_nat_gateway" not in terraform
    assert "aws_eks_cluster" not in terraform
    assert "aws_msk" not in terraform


def test_bootstrap_contains_no_runtime_secret_value() -> None:
    bootstrap = (TF_DIR / "user_data.sh.tftpl").read_text()

    assert "POSTGRES_PASSWORD" not in bootstrap
    assert "API_KEY" not in bootstrap
    assert "oauth" not in bootstrap.lower()


@pytest.mark.parametrize(
    "forbidden",
    (
        "terraform apply -auto-approve",
        "latest",
        "0.0.0.0:8080:8080",
    ),
)
def test_cloud_artifacts_avoid_unsafe_shortcuts(forbidden: str) -> None:
    sources = COMPOSE_FILE.read_text() + "\n" + (
        TF_DIR / "user_data.sh.tftpl"
    ).read_text()

    assert forbidden not in sources

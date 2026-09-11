#!/usr/bin/env python3
"""Guarded operator commands for the temporary Argus EC2 learning smoke."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
TF_DIR = ROOT / "infra" / "terraform" / "aws-ec2-smoke"
PLAN_FILE = TF_DIR / "argus-ec2-smoke.tfplan"
COMPOSE_FILE = ROOT / "compose.aws-ec2.yaml"
REGION = "us-west-2"
DEFAULT_PROFILE = "argus-login"
BACKEND_REPOSITORY = "argus-ec2-smoke-backend"
FRONTEND_REPOSITORY = "argus-ec2-smoke-frontend"
APPLY_CONFIRMATION = "CREATE-ARGUS-EC2-SMOKE"
DESTROY_CONFIRMATION = "DESTROY-ARGUS-EC2-SMOKE"
MAX_RUNTIME_SECONDS = 6 * 60 * 60

ACCOUNT_ID_PATTERN = re.compile(r"(?<!\d)\d{12}(?!\d)")


class CommandError(RuntimeError):
    pass


def _sanitize(value: str) -> str:
    return ACCOUNT_ID_PATTERN.sub("<redacted-account>", value)


def _run(
    command: Sequence[str],
    *,
    capture: bool = False,
    check: bool = True,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        input=input_text,
        capture_output=capture,
        text=True,
    )
    if check and result.returncode != 0:
        detail = _sanitize((result.stderr or result.stdout or "").strip())
        if not detail:
            detail = f"exit code {result.returncode}"
        raise CommandError(f"Command failed: {command[0]} ({detail})")
    return result


def _capture(command: Sequence[str], **kwargs: object) -> str:
    result = _run(command, capture=True, **kwargs)
    return result.stdout.strip()


def _aws(profile: str, *arguments: str, check: bool = True) -> str:
    return _capture(
        ["aws", *arguments, "--profile", profile, "--region", REGION],
        check=check,
    )


def _terraform_environment(profile: str) -> dict[str, str]:
    """Translate an AWS CLI login session into child-only environment credentials."""
    exported = json.loads(
        _capture(
            [
                "aws",
                "configure",
                "export-credentials",
                "--profile",
                profile,
                "--format",
                "process",
            ]
        )
    )
    environment = os.environ.copy()
    environment.pop("AWS_PROFILE", None)
    environment.pop("AWS_DEFAULT_PROFILE", None)
    environment.update(
        {
            "AWS_ACCESS_KEY_ID": exported["AccessKeyId"],
            "AWS_SECRET_ACCESS_KEY": exported["SecretAccessKey"],
            "AWS_SESSION_TOKEN": exported["SessionToken"],
            "AWS_REGION": REGION,
            "AWS_DEFAULT_REGION": REGION,
        }
    )
    return environment


def _terraform(
    *arguments: str,
    capture: bool = False,
    profile: str | None = None,
) -> str:
    command = ["terraform", f"-chdir={TF_DIR}", *arguments]
    environment = _terraform_environment(profile) if profile else None
    if capture:
        return _capture(command, env=environment)
    _run(command, env=environment)
    return ""


def _plan_sha256() -> str:
    return hashlib.sha256(PLAN_FILE.read_bytes()).hexdigest()


def _require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise CommandError(f"Missing required command: {name}")


def _parse_deadline(value: str) -> datetime:
    try:
        deadline = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CommandError(
            "ARGUS_HARD_DESTROY_AT must be ISO 8601 with a UTC offset, "
            "for example 2026-07-24T21:00:00-07:00."
        ) from exc
    if deadline.tzinfo is None:
        raise CommandError("ARGUS_HARD_DESTROY_AT must include a UTC offset.")
    return deadline


def _require_live_approval() -> datetime:
    if os.getenv("ARGUS_AWS_APPLY_APPROVED") != APPLY_CONFIRMATION:
        raise CommandError(
            f"Set ARGUS_AWS_APPLY_APPROVED={APPLY_CONFIRMATION} only after plan approval."
        )
    approved_sha = os.getenv("ARGUS_APPROVED_PLAN_SHA256", "")
    actual_sha = _plan_sha256()
    if approved_sha != actual_sha:
        raise CommandError("Approved plan SHA-256 does not match the saved plan.")
    deadline = _parse_deadline(os.getenv("ARGUS_HARD_DESTROY_AT", ""))
    now = datetime.now(deadline.tzinfo)
    seconds_remaining = (deadline - now).total_seconds()
    if seconds_remaining <= 0:
        raise CommandError("The hard destroy time has already passed.")
    if seconds_remaining > MAX_RUNTIME_SECONDS:
        raise CommandError("The hard destroy time may be no more than six hours away.")
    return deadline


def _require_before_deadline() -> datetime:
    value = os.getenv("ARGUS_HARD_DESTROY_AT", "")
    deadline = _parse_deadline(value)
    if datetime.now(deadline.tzinfo) >= deadline:
        raise CommandError("Hard destroy time reached: run destroy before more testing.")
    return deadline


def _tf_output(name: str) -> str:
    return _terraform("output", "-raw", name, capture=True)


def _repository_uri(profile: str, repository: str) -> str:
    return _aws(
        profile,
        "ecr",
        "describe-repositories",
        "--repository-names",
        repository,
        "--query",
        "repositories[0].repositoryUri",
        "--output",
        "text",
    )


def doctor(profile: str) -> None:
    for command in ("aws", "terraform", "docker", "git"):
        _require_command(command)
    _aws(profile, "sts", "get-caller-identity")
    _run(["docker", "info"], capture=True)

    print("AWS IAM session: valid (identity intentionally not printed)")
    print(f"AWS Region: {REGION}")
    print(_capture(["terraform", "version"]).splitlines()[0])
    print(_capture(["docker", "version", "--format", "Docker {{.Client.Version}}"]))
    print(_capture(["git", "rev-parse", "--short=12", "HEAD"]))
    plugin = shutil.which("session-manager-plugin")
    print(
        "Session Manager plugin: installed"
        if plugin
        else "Session Manager plugin: MISSING (install before the port-forward video)"
    )


def plan(profile: str) -> None:
    _aws(profile, "sts", "get-caller-identity")
    _terraform("init", "-input=false", "-upgrade=false")
    _terraform(
        "plan",
        "-input=false",
        "-out",
        str(PLAN_FILE),
        profile=profile,
    )
    print(f"Saved plan SHA-256: {_plan_sha256()}")
    print("STOP: review this plan, current credits, budget, and hard destroy time.")
    print("No AWS resources were created.")


def apply_saved_plan(profile: str) -> None:
    deadline = _require_live_approval()
    _aws(profile, "sts", "get-caller-identity")
    print("Applying the exact approved plan; AWS identifiers stay hidden.")
    _terraform(
        "apply",
        "-input=false",
        str(PLAN_FILE),
        profile=profile,
        capture=True,
    )
    print("Temporary infrastructure created from the exact approved plan.")
    print(f"Hard destroy deadline: {deadline.isoformat()}")


def build_and_push(profile: str) -> None:
    _require_before_deadline()
    if _capture(["git", "status", "--porcelain"]):
        raise CommandError("Worktree is not clean; commit before building auditable images.")
    sha = _capture(["git", "rev-parse", "--short=12", "HEAD"])
    tag = f"sha-{sha}"
    backend_uri = _repository_uri(profile, BACKEND_REPOSITORY)
    frontend_uri = _repository_uri(profile, FRONTEND_REPOSITORY)
    registry = backend_uri.split("/", 1)[0]

    password = _aws(profile, "ecr", "get-login-password")
    _run(
        ["docker", "login", "--username", "AWS", "--password-stdin", registry],
        capture=True,
        input_text=password,
    )

    print(f"Building backend linux/amd64 image with immutable tag {tag}...")
    _run(
        [
            "docker",
            "buildx",
            "build",
            "--platform",
            "linux/amd64",
            "--push",
            "--quiet",
            "--tag",
            f"{backend_uri}:{tag}",
            ".",
        ],
        capture=True,
    )
    print(f"Building frontend linux/amd64 image with immutable tag {tag}...")
    _run(
        [
            "docker",
            "buildx",
            "build",
            "--platform",
            "linux/amd64",
            "--push",
            "--quiet",
            "--file",
            "frontend/Dockerfile.prod",
            "--tag",
            f"{frontend_uri}:{tag}",
            "frontend",
        ],
        capture=True,
    )
    print(f"Pushed backend and frontend images tagged {tag}.")


def _send_ssm(
    profile: str,
    commands: list[str],
    *,
    comment: str,
    show_output: bool,
) -> None:
    instance_id = _tf_output("instance_id")
    command_id = _aws(
        profile,
        "ssm",
        "send-command",
        "--instance-ids",
        instance_id,
        "--document-name",
        "AWS-RunShellScript",
        "--comment",
        comment,
        "--parameters",
        json.dumps({"commands": commands}),
        "--query",
        "Command.CommandId",
        "--output",
        "text",
    )
    _aws(
        profile,
        "ssm",
        "wait",
        "command-executed",
        "--command-id",
        command_id,
        "--instance-id",
        instance_id,
        check=False,
    )
    invocation = json.loads(
        _aws(
            profile,
            "ssm",
            "get-command-invocation",
            "--command-id",
            command_id,
            "--instance-id",
            instance_id,
            "--output",
            "json",
        )
    )
    if show_output and invocation.get("StandardOutputContent"):
        print(_sanitize(invocation["StandardOutputContent"].rstrip()))
    if invocation.get("Status") != "Success":
        error = _sanitize(invocation.get("StandardErrorContent", "").rstrip())
        raise CommandError(f"SSM command failed: {error}")


def deploy(profile: str) -> None:
    _require_before_deadline()
    sha = _capture(["git", "rev-parse", "--short=12", "HEAD"])
    tag = f"sha-{sha}"
    backend_uri = _repository_uri(profile, BACKEND_REPOSITORY)
    frontend_uri = _repository_uri(profile, FRONTEND_REPOSITORY)
    registry = backend_uri.split("/", 1)[0]
    compose_b64 = base64.b64encode(COMPOSE_FILE.read_bytes()).decode("ascii")

    commands = [
        "set -euo pipefail",
        "test -f /var/lib/argus-bootstrap-complete",
        "install -d -o root -g root -m 0700 /opt/argus",
        f"printf '%s' '{compose_b64}' | base64 --decode > /opt/argus/compose.yaml",
        (
            "if [ ! -f /opt/argus/.env ]; then "
            "umask 077; POSTGRES_PASSWORD=$(openssl rand -hex 24); "
            "printf 'POSTGRES_PASSWORD=%s\\nARGUS_BACKEND_IMAGE=%s\\n"
            "ARGUS_FRONTEND_IMAGE=%s\\n' "
            f'"$POSTGRES_PASSWORD" "{backend_uri}:{tag}" "{frontend_uri}:{tag}" '
            "> /opt/argus/.env; fi"
        ),
        "chmod 0600 /opt/argus/.env",
        (
            f"aws ecr get-login-password --region {REGION} | "
            f"docker login --username AWS --password-stdin '{registry}' >/dev/null 2>&1"
        ),
        (
            "cd /opt/argus && "
            "docker compose --env-file .env -f compose.yaml pull --quiet"
        ),
        (
            "cd /opt/argus && docker compose --env-file .env -f compose.yaml "
            "up -d --remove-orphans --wait"
        ),
        "docker image prune --force >/dev/null",
        "echo 'Compose deployment reached healthy/running state.'",
    ]
    _send_ssm(
        profile,
        commands,
        comment="Deploy Argus immutable smoke images",
        show_output=True,
    )


def accept(profile: str) -> None:
    _require_before_deadline()
    commands = [
        "set -euo pipefail",
        "cd /opt/argus",
        "echo 'Running services:'",
        (
            "docker compose --env-file .env -f compose.yaml ps --services "
            "--filter status=running | sort"
        ),
        "docker compose --env-file .env -f compose.yaml exec -T argus-api argus-verify-migration",
        (
            "docker compose --env-file .env -f compose.yaml exec -T argus-api "
            "python /app/scripts/kafka_local_acceptance.py "
            "--bootstrap kafka:9092 --api-base http://localhost:8000"
        ),
        (
            "docker compose --env-file .env -f compose.yaml exec -T kafka "
            "/opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 "
            "--group argus-audit-metrics-v1 --describe"
        ),
    ]
    _send_ssm(
        profile,
        commands,
        comment="Run Argus migration and Kafka acceptance",
        show_output=True,
    )


def port_forward(profile: str) -> None:
    _require_before_deadline()
    _require_command("session-manager-plugin")
    instance_id = _tf_output("instance_id")
    print("Open http://127.0.0.1:18080 and press Control+C when recording is done.")
    try:
        _run(
            [
                "aws",
                "ssm",
                "start-session",
                "--target",
                instance_id,
                "--document-name",
                "AWS-StartPortForwardingSession",
                "--parameters",
                "portNumber=8080,localPortNumber=18080",
                "--profile",
                profile,
                "--region",
                REGION,
            ]
        )
    except KeyboardInterrupt:
        print("\nSSM port-forward closed; the EC2 services are still running.")


def _count(profile: str, label: str, *aws_arguments: str) -> None:
    try:
        value = _aws(profile, *aws_arguments)
    except CommandError:
        print(f"{label}: unavailable for this account/plan")
    else:
        print(f"{label}: {_sanitize(value)}")


def residual(profile: str) -> None:
    print("Independent residual audit (expected count is 0 after destroy):")
    _count(
        profile,
        "EC2",
        "ec2",
        "describe-instances",
        "--filters",
        "Name=tag:Stack,Values=ec2-smoke",
        "Name=instance-state-name,Values=pending,running,stopping,stopped",
        "--query",
        "length(Reservations[].Instances[])",
        "--output",
        "text",
    )
    _count(
        profile,
        "VPC",
        "ec2",
        "describe-vpcs",
        "--filters",
        "Name=tag:Stack,Values=ec2-smoke",
        "--query",
        "length(Vpcs)",
        "--output",
        "text",
    )
    _count(
        profile,
        "NAT gateways",
        "ec2",
        "describe-nat-gateways",
        "--filter",
        "Name=tag:Project,Values=argus",
        "Name=state,Values=pending,available,deleting",
        "--query",
        "length(NatGateways)",
        "--output",
        "text",
    )
    _count(
        profile,
        "EBS volumes",
        "ec2",
        "describe-volumes",
        "--filters",
        "Name=tag:Project,Values=argus",
        "Name=status,Values=creating,available,in-use,deleting,error",
        "--query",
        "length(Volumes)",
        "--output",
        "text",
    )
    _count(
        profile,
        "ECR repositories",
        "ecr",
        "describe-repositories",
        "--query",
        "length(repositories[?starts_with(repositoryName, 'argus-ec2-smoke-')])",
        "--output",
        "text",
    )
    _count(
        profile,
        "EKS clusters",
        "eks",
        "list-clusters",
        "--query",
        "length(clusters[?contains(@, 'argus')])",
        "--output",
        "text",
    )
    _count(
        profile,
        "MSK clusters",
        "kafka",
        "list-clusters-v2",
        "--query",
        "length(ClusterInfoList[?contains(ClusterName, 'argus')])",
        "--output",
        "text",
    )
    _count(
        profile,
        "RDS instances",
        "rds",
        "describe-db-instances",
        "--query",
        "length(DBInstances[?contains(DBInstanceIdentifier, 'argus')])",
        "--output",
        "text",
    )
    _count(
        profile,
        "ElastiCache clusters",
        "elasticache",
        "describe-cache-clusters",
        "--query",
        "length(CacheClusters[?contains(CacheClusterId, 'argus')])",
        "--output",
        "text",
    )
    _count(
        profile,
        "S3 buckets",
        "s3api",
        "list-buckets",
        "--query",
        "length(Buckets[?contains(Name, 'argus')])",
        "--output",
        "text",
    )
    _count(
        profile,
        "Secrets Manager secrets",
        "secretsmanager",
        "list-secrets",
        "--filters",
        "Key=name,Values=argus",
        "--query",
        "length(SecretList)",
        "--output",
        "text",
    )
    account_id = _aws(
        profile,
        "sts",
        "get-caller-identity",
        "--query",
        "Account",
        "--output",
        "text",
    )
    _count(
        profile,
        "AWS Budgets",
        "budgets",
        "describe-budgets",
        "--account-id",
        account_id,
        "--query",
        "length(not_null(Budgets, `[]`)[?contains(BudgetName, 'argus-learning-ec2-smoke')])",
        "--output",
        "text",
    )
    try:
        state_resources = _terraform("state", "list", capture=True)
    except CommandError:
        state_resources = ""
    count = len([line for line in state_resources.splitlines() if line.strip()])
    print(f"Terraform state resources: {count}")


def destroy(profile: str, confirmation: str) -> None:
    if confirmation != DESTROY_CONFIRMATION:
        raise CommandError(
            f"Destroy requires --confirm {DESTROY_CONFIRMATION}."
        )
    print("Destroying only resources recorded in the EC2 smoke Terraform state...")
    _terraform(
        "destroy",
        "-auto-approve",
        "-input=false",
        profile=profile,
        capture=True,
    )
    print("Terraform destroy completed; now checking independent residuals.")
    residual(profile)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Operate the reviewed Argus EC2 smoke without printing credentials."
    )
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in (
        "doctor",
        "plan",
        "apply",
        "build-push",
        "deploy",
        "accept",
        "port-forward",
        "residual",
    ):
        subparsers.add_parser(name)
    destroy_parser = subparsers.add_parser("destroy")
    destroy_parser.add_argument("--confirm", required=True)
    args = parser.parse_args()

    actions = {
        "doctor": lambda: doctor(args.profile),
        "plan": lambda: plan(args.profile),
        "apply": lambda: apply_saved_plan(args.profile),
        "build-push": lambda: build_and_push(args.profile),
        "deploy": lambda: deploy(args.profile),
        "accept": lambda: accept(args.profile),
        "port-forward": lambda: port_forward(args.profile),
        "residual": lambda: residual(args.profile),
        "destroy": lambda: destroy(args.profile, args.confirm),
    }
    try:
        actions[args.command]()
    except (CommandError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ERROR: {_sanitize(str(exc))}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

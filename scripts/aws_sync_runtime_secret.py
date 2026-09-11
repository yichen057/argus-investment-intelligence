#!/usr/bin/env python3
"""Safely sync one answer model and Exa into AWS/Kubernetes runtime secrets."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

RUNTIME_BASE_KEYS = frozenset(
    {
        "ARGUS_DATABASE_URL",
        "ARGUS_REDIS_URL",
        "ARGUS_S3_BUCKET",
        "ARGUS_KAFKA_BOOTSTRAP_SERVERS",
        "ARGUS_KAFKA_SECURITY_PROTOCOL",
        "ARGUS_KAFKA_SASL_MECHANISM",
    }
)
AUTHORIZED_PROVIDER_SECRET_KEYS = frozenset(
    {
        "ARGUS_GEMINI_API_KEY",
        "ARGUS_EXA_API_KEY",
    }
)


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "command failed without stderr"
        raise RuntimeError(f"{command[0]} failed: {detail}")
    return result.stdout


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _write_private(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    os.chmod(path, 0o600)


def _terraform_output(terraform_dir: Path, name: str) -> str:
    return _run(
        ["terraform", "output", "-raw", name], cwd=terraform_dir
    ).strip()


def _load_runtime_secret(
    *, secret_arn: str, profile: str, region: str
) -> dict[str, Any]:
    raw_secret = _run(
        [
            "aws",
            "secretsmanager",
            "get-secret-value",
            "--secret-id",
            secret_arn,
            "--profile",
            profile,
            "--region",
            region,
            "--query",
            "SecretString",
            "--output",
            "text",
        ]
    )
    value = json.loads(raw_secret)
    if not isinstance(value, dict):
        raise RuntimeError("AWS runtime secret must contain a JSON object")
    return value


def _build_runtime_values(
    current_values: dict[str, Any],
    env_values: dict[str, str],
) -> dict[str, str]:
    runtime_values: dict[str, str] = {}
    for key in RUNTIME_BASE_KEYS:
        value = current_values.get(key)
        if not isinstance(value, str):
            raise RuntimeError(f"AWS runtime secret is missing string field {key}")
        runtime_values[key] = value
    for key in AUTHORIZED_PROVIDER_SECRET_KEYS:
        value = env_values.get(key, "")
        if not value:
            raise RuntimeError(f"{key} is missing from the env file")
        runtime_values[key] = value
    return runtime_values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    repo_root = Path(__file__).resolve().parents[1]
    parser.add_argument("--profile", default="argus-terraform")
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--namespace", default="argus")
    parser.add_argument("--kubernetes-secret", default="argus-secrets")
    parser.add_argument("--env-file", type=Path, default=repo_root / ".env")
    parser.add_argument(
        "--terraform-dir",
        type=Path,
        default=repo_root / "infra" / "terraform" / "aws",
    )
    args = parser.parse_args()

    env_values = _read_env(args.env_file)

    secret_arn = _terraform_output(args.terraform_dir, "runtime_secret_arn")
    runtime_values = _build_runtime_values(
        _load_runtime_secret(
            secret_arn=secret_arn,
            profile=args.profile,
            region=args.region,
        ),
        env_values,
    )

    for key, value in runtime_values.items():
        if "\n" in value or "\r" in value:
            raise RuntimeError(f"Runtime secret value for {key} contains a newline")

    with tempfile.TemporaryDirectory(prefix="argus-secret-") as temp_dir:
        temp_path = Path(temp_dir)
        os.chmod(temp_path, 0o700)
        json_path = temp_path / "runtime.json"
        env_path = temp_path / "runtime.env"
        _write_private(
            json_path,
            json.dumps(runtime_values, separators=(",", ":")),
        )
        _write_private(
            env_path,
            "".join(
                f"{key}={value}\n" for key, value in sorted(runtime_values.items())
            ),
        )

        _run(
            [
                "aws",
                "secretsmanager",
                "put-secret-value",
                "--secret-id",
                secret_arn,
                "--secret-string",
                f"file://{json_path}",
                "--profile",
                args.profile,
                "--region",
                args.region,
            ]
        )

        namespace_manifest = _run(
            [
                "kubectl",
                "create",
                "namespace",
                args.namespace,
                "--dry-run=client",
                "-o",
                "json",
            ]
        )
        _run(["kubectl", "apply", "-f", "-"], input_text=namespace_manifest)
        secret_manifest = _run(
            [
                "kubectl",
                "-n",
                args.namespace,
                "create",
                "secret",
                "generic",
                args.kubernetes_secret,
                f"--from-env-file={env_path}",
                "--dry-run=client",
                "-o",
                "json",
            ]
        )
        _run(["kubectl", "apply", "-f", "-"], input_text=secret_manifest)

    print(
        f"Synced {len(runtime_values)} runtime variables to AWS Secrets Manager "
        f"and {args.namespace}/{args.kubernetes_secret}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

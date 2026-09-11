from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import StringIO
from pathlib import PurePosixPath
import re
from typing import Any
from zipfile import BadZipFile, ZipFile
from io import BytesIO

_MAX_ARCHIVE_BYTES = 5 * 1024 * 1024
_MAX_UNCOMPRESSED_BYTES = 10 * 1024 * 1024
_MAX_CSV_ROWS = 100_000
_PERIOD_PATTERN = re.compile(
    r"^(?:cost|amount)-(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.csv$"
)
_TOKEN_TYPES = {
    "input_cache_hit_tokens",
    "input_cache_miss_tokens",
    "input_tokens",
    "output_tokens",
}


class DeepSeekExportError(ValueError):
    """Raised when a DeepSeek usage export cannot be imported safely."""


@dataclass(frozen=True)
class DeepSeekExportSummary:
    period_start: date
    period_end: date
    currency: str
    actual_cost: Decimal
    total_tokens: int
    request_count: int
    content_sha256: str
    metadata: dict[str, Any]


def parse_deepseek_usage_export(
    archive: bytes,
    *,
    source_filename: str,
) -> DeepSeekExportSummary:
    """Parse a bounded DeepSeek ZIP without retaining identity or API-key columns."""

    if not archive:
        raise DeepSeekExportError("The DeepSeek export is empty.")
    if len(archive) > _MAX_ARCHIVE_BYTES:
        raise DeepSeekExportError("The DeepSeek export exceeds the 5 MB import limit.")

    try:
        with ZipFile(BytesIO(archive)) as bundle:
            members = [item for item in bundle.infolist() if not item.is_dir()]
            if not members or len(members) > 10:
                raise DeepSeekExportError(
                    "The DeepSeek export must contain the expected bounded CSV files."
                )
            if sum(item.file_size for item in members) > _MAX_UNCOMPRESSED_BYTES:
                raise DeepSeekExportError(
                    "The uncompressed DeepSeek export exceeds the 10 MB limit."
                )
            for item in members:
                path = PurePosixPath(item.filename)
                if path.name != item.filename or path.suffix.lower() != ".csv":
                    raise DeepSeekExportError(
                        "The DeepSeek export contains an unexpected path or file type."
                    )

            cost_member = _single_member(members, prefix="cost-")
            amount_member = _single_member(members, prefix="amount-")
            cost_text = bundle.read(cost_member).decode("utf-8-sig")
            amount_text = bundle.read(amount_member).decode("utf-8-sig")
    except BadZipFile as exc:
        raise DeepSeekExportError("The uploaded file is not a valid ZIP export.") from exc
    except UnicodeDecodeError as exc:
        raise DeepSeekExportError("The DeepSeek CSV files must use UTF-8 text.") from exc

    cost_period = _period_from_name(cost_member.filename)
    amount_period = _period_from_name(amount_member.filename)
    if cost_period != amount_period:
        raise DeepSeekExportError("The cost and amount CSV periods do not match.")

    cost_rows = _csv_rows(cost_text)
    amount_rows = _csv_rows(amount_text)
    currencies = {
        str(row.get("currency") or "").strip().upper()
        for row in cost_rows
        if str(row.get("currency") or "").strip()
    }
    if len(currencies) != 1:
        raise DeepSeekExportError(
            "A DeepSeek import must contain exactly one billing currency."
        )
    currency = next(iter(currencies))

    model_stats: dict[str, dict[str, Any]] = {}
    total_cost = Decimal("0")
    row_dates: list[date] = []
    for row in cost_rows:
        model = _model_name(row)
        try:
            cost = Decimal(str(row.get("cost") or "0"))
        except InvalidOperation as exc:
            raise DeepSeekExportError("A DeepSeek cost row is not numeric.") from exc
        if cost < 0:
            raise DeepSeekExportError("DeepSeek cost rows cannot be negative.")
        total_cost += cost
        stats = model_stats.setdefault(model, _empty_model_stats())
        stats["actual_cost"] += cost
        parsed_date = _compact_date(row.get("utc_date"))
        if parsed_date is not None:
            row_dates.append(parsed_date)

    for row in amount_rows:
        model = _model_name(row)
        metric = str(row.get("type") or "").strip()
        if metric not in _TOKEN_TYPES | {"request_count"}:
            continue
        try:
            amount = int(Decimal(str(row.get("amount") or "0")))
        except (InvalidOperation, ValueError) as exc:
            raise DeepSeekExportError("A DeepSeek amount row is not numeric.") from exc
        if amount < 0:
            raise DeepSeekExportError("DeepSeek usage rows cannot be negative.")
        stats = model_stats.setdefault(model, _empty_model_stats())
        stats[metric] += amount
        parsed_date = _compact_date(row.get("utc_date"))
        if parsed_date is not None:
            row_dates.append(parsed_date)

    request_count = sum(int(item["request_count"]) for item in model_stats.values())
    total_tokens = sum(
        sum(int(item[name]) for name in _TOKEN_TYPES)
        for item in model_stats.values()
    )
    if request_count <= 0:
        raise DeepSeekExportError("The DeepSeek export contains no request count.")

    breakdown = []
    for model, stats in sorted(model_stats.items()):
        model_tokens = sum(int(stats[name]) for name in _TOKEN_TYPES)
        breakdown.append(
            {
                "model": model,
                "request_count": int(stats["request_count"]),
                "input_cache_hit_tokens": int(stats["input_cache_hit_tokens"]),
                "input_cache_miss_tokens": int(stats["input_cache_miss_tokens"]),
                "input_tokens": int(stats["input_tokens"]),
                "output_tokens": int(stats["output_tokens"]),
                "total_tokens": model_tokens,
                "actual_cost": format(stats["actual_cost"], "f"),
            }
        )

    period_start, end_exclusive = cost_period
    content_digest = sha256(archive).hexdigest()
    metadata: dict[str, Any] = {
        "import_kind": "deepseek_official_usage_export",
        "source_filename": PurePosixPath(source_filename).name,
        "export_end_is_exclusive": True,
        "content_sha256": content_digest,
        "model_breakdown": breakdown,
        "ignored_sensitive_columns": ["user_id", "api_key", "api_key_name"],
    }
    if row_dates:
        metadata["first_usage_date"] = min(row_dates).isoformat()
        metadata["last_usage_date"] = max(row_dates).isoformat()

    return DeepSeekExportSummary(
        period_start=period_start,
        period_end=end_exclusive - timedelta(days=1),
        currency=currency,
        actual_cost=total_cost,
        total_tokens=total_tokens,
        request_count=request_count,
        content_sha256=content_digest,
        metadata=metadata,
    )


def _single_member(members: list[Any], *, prefix: str) -> Any:
    matches = [item for item in members if item.filename.startswith(prefix)]
    if len(matches) != 1:
        raise DeepSeekExportError(
            f"The DeepSeek export must contain exactly one {prefix.rstrip('-')} CSV."
        )
    return matches[0]


def _period_from_name(filename: str) -> tuple[date, date]:
    match = _PERIOD_PATTERN.fullmatch(filename)
    if match is None:
        raise DeepSeekExportError("The DeepSeek CSV filename has an unknown period.")
    start = date.fromisoformat(match.group(1))
    end_exclusive = date.fromisoformat(match.group(2))
    if end_exclusive <= start:
        raise DeepSeekExportError("The DeepSeek export period is invalid.")
    return start, end_exclusive


def _csv_rows(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(StringIO(text))
    rows: list[dict[str, str]] = []
    for index, row in enumerate(reader, start=1):
        if index > _MAX_CSV_ROWS:
            raise DeepSeekExportError("The DeepSeek CSV exceeds the row limit.")
        rows.append({str(key): str(value or "") for key, value in row.items()})
    if not rows:
        raise DeepSeekExportError("A required DeepSeek CSV contains no data rows.")
    return rows


def _model_name(row: dict[str, str]) -> str:
    model = str(row.get("model") or "").strip()
    if not model or len(model) > 256:
        raise DeepSeekExportError("A DeepSeek row has an invalid model name.")
    return model


def _compact_date(value: Any) -> date | None:
    normalized = str(value or "").strip()
    if not re.fullmatch(r"\d{8}", normalized):
        return None
    return date(int(normalized[:4]), int(normalized[4:6]), int(normalized[6:8]))


def _empty_model_stats() -> dict[str, Any]:
    return {
        "request_count": 0,
        "input_cache_hit_tokens": 0,
        "input_cache_miss_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "actual_cost": Decimal("0"),
    }

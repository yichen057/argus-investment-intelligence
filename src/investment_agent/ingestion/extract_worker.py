from __future__ import annotations

import argparse
import codecs
import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any, Sequence

from pypdf import PdfReader


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Argus isolated document extractor")
    parser.add_argument("--input", required=True)
    parser.add_argument("--source-type", required=True)
    parser.add_argument("--pages-output", required=True)
    parser.add_argument("--status-output", required=True)
    parser.add_argument("--max-pages", type=int, required=True)
    parser.add_argument("--max-characters", type=int, required=True)
    args = parser.parse_args(argv)
    status_path = Path(args.status_output)
    try:
        result = extract_document(
            Path(args.input),
            source_type=args.source_type,
            pages_path=Path(args.pages_output),
            max_pages=args.max_pages,
            max_characters=args.max_characters,
        )
        _write_status(status_path, {"status": "ok", **result})
    except WorkerLimitError as exc:
        _write_status(status_path, {"status": "error", **exc.payload})
        raise SystemExit(2) from None
    except UnicodeDecodeError:
        _write_status(
            status_path,
            {
                "status": "error",
                "code": "invalid_utf8",
                "message": "File is not valid UTF-8 text.",
                "stage": "extract",
                "next_action": "Save the source as UTF-8 or upload a searchable PDF.",
                "status_code": 422,
            },
        )
        raise SystemExit(2) from None
    except Exception as exc:
        _write_status(
            status_path,
            {
                "status": "error",
                "code": "document_parse_failed",
                "message": f"The isolated parser could not read this document: {exc}",
                "stage": "extract",
                "next_action": "Convert the source to searchable UTF-8 text or PDF, then retry.",
                "status_code": 422,
            },
        )
        raise SystemExit(2) from None


class WorkerLimitError(RuntimeError):
    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__(str(payload.get("message")))
        self.payload = payload


def extract_document(
    path: Path,
    *,
    source_type: str,
    pages_path: Path,
    max_pages: int,
    max_characters: int,
) -> dict[str, object]:
    if source_type in {"text", "markdown", "csv"}:
        text = _read_utf8_bounded(path, max_characters=max_characters)
        dataset_metadata = _csv_metadata(text) if source_type == "csv" else {}
        _write_page(
            pages_path,
            page_number=1,
            section_label="dataset rows" if source_type == "csv" else "full document",
            text=text,
        )
        return {
            "page_count": 1,
            "extracted_characters": len(text),
            "dataset_metadata": dataset_metadata,
        }
    if source_type != "pdf":
        raise ValueError(f"Unsupported source type: {source_type}")

    reader = PdfReader(path)
    physical_pages = len(reader.pages)
    if physical_pages > max_pages:
        raise WorkerLimitError(
            {
                "code": "pdf_page_limit_exceeded",
                "message": "PDF parsing stopped because the document has too many pages.",
                "stage": "extract",
                "observed": physical_pages,
                "limit": max_pages,
                "next_action": "Split the PDF into smaller topic-focused files, then retry.",
                "status_code": 413,
            }
        )
    page_count = 0
    extracted_characters = 0
    pages_path.parent.mkdir(parents=True, exist_ok=True)
    with pages_path.open("w", encoding="utf-8") as handle:
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                continue
            extracted_characters += len(text)
            if extracted_characters > max_characters:
                raise WorkerLimitError(
                    {
                        "code": "extracted_text_limit_exceeded",
                        "message": "PDF parsing stopped because extracted text exceeded the safe limit.",
                        "stage": "extract",
                        "observed": extracted_characters,
                        "limit": max_characters,
                        "next_action": "Split the PDF or upload only the relevant chapters.",
                        "status_code": 413,
                    }
                )
            handle.write(
                json.dumps(
                    {
                        "page_number": index,
                        "section_label": f"page {index}",
                        "text": text,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            page_count += 1
    if page_count == 0:
        raise ValueError(
            "This PDF has no extractable text layer. It is probably scanned or image-only; run OCR first."
        )
    return {
        "page_count": page_count,
        "extracted_characters": extracted_characters,
        "dataset_metadata": {},
    }


def _read_utf8_bounded(path: Path, *, max_characters: int) -> str:
    decoder = codecs.getincrementaldecoder("utf-8")()
    parts: list[str] = []
    count = 0
    with path.open("rb") as handle:
        while chunk := handle.read(64 * 1024):
            decoded = decoder.decode(chunk)
            count += len(decoded)
            if count > max_characters:
                raise WorkerLimitError(
                    {
                        "code": "extracted_text_limit_exceeded",
                        "message": "Text extraction stopped because the document exceeded the safe text limit.",
                        "stage": "extract",
                        "observed": count,
                        "limit": max_characters,
                        "next_action": "Split the document into smaller files, then retry.",
                        "status_code": 413,
                    }
                )
            parts.append(decoded)
        tail = decoder.decode(b"", final=True)
        count += len(tail)
        parts.append(tail)
    return "".join(parts)


def _write_page(
    pages_path: Path,
    *,
    page_number: int,
    section_label: str,
    text: str,
) -> None:
    pages_path.parent.mkdir(parents=True, exist_ok=True)
    pages_path.write_text(
        json.dumps(
            {
                "page_number": page_number,
                "section_label": section_label,
                "text": text,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _csv_metadata(text: str) -> dict[str, object]:
    reader = csv.DictReader(StringIO(text))
    fieldnames = [field.strip() for field in (reader.fieldnames or []) if field.strip()]
    if not fieldnames:
        raise ValueError("CSV source requires a header row.")
    row_count = sum(
        1 for row in reader if any((value or "").strip() for value in row.values())
    )
    if row_count == 0:
        raise ValueError("CSV source requires at least one data row.")
    return {
        "columns": fieldnames,
        "column_count": len(fieldnames),
        "row_count": row_count,
    }


def _write_status(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()

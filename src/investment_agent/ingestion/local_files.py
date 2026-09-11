from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from investment_agent.ingestion.chunking import chunk_text
from investment_agent.ingestion.resources import (
    DocumentResourceError,
    DocumentResourcePolicy,
    ExtractionArtifact,
    extract_in_bounded_process,
)
from investment_agent.repositories.documents import (
    ChunkCreate,
    DocumentCreate,
    DocumentRepository,
    EvidenceItemCreate,
)


class UnsupportedSourceType(ValueError):
    pass


@dataclass(frozen=True)
class IngestedDocument:
    document_id: int
    content_hash: str
    created: bool
    evidence_count: int
    chunk_count: int


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    section_label: str
    text: str


class LocalFileIngestor:
    def __init__(
        self,
        session: Session,
        *,
        chunk_size: int = 1200,
        overlap: int = 120,
        resource_policy: DocumentResourcePolicy | None = None,
    ) -> None:
        self._repository = DocumentRepository(session)
        self._chunk_size = chunk_size
        self._overlap = overlap
        self._resource_policy = resource_policy or DocumentResourcePolicy()

    def ingest_path(self, path: Path) -> IngestedDocument:
        resolved_path = path.expanduser().resolve()
        if not resolved_path.is_file():
            raise FileNotFoundError(str(resolved_path))

        source_type = _source_type_for_suffix(resolved_path.suffix)
        raw_bytes = resolved_path.stat().st_size
        if raw_bytes > self._resource_policy.max_upload_bytes:
            raise DocumentResourceError(
                "upload_too_large",
                "Document ingestion stopped because the source file exceeds the upload limit.",
                stage="upload",
                observed=raw_bytes,
                limit=self._resource_policy.max_upload_bytes,
                next_action="Split or compress the source file, then retry.",
                status_code=413,
            )
        content_hash = _sha256_path(resolved_path)

        existing = self._repository.get_document_by_hash(content_hash)
        if existing is not None:
            return IngestedDocument(
                document_id=existing.id,
                content_hash=content_hash,
                created=False,
                evidence_count=len(
                    self._repository.list_evidence_for_document(existing.id)
                ),
                chunk_count=len(self._repository.list_chunks_for_document(existing.id)),
            )

        extraction = extract_in_bounded_process(
            resolved_path,
            source_type,
            self._resource_policy,
        )
        try:
            return self._persist_extraction(
                resolved_path,
                source_type=source_type,
                content_hash=content_hash,
                raw_bytes=raw_bytes,
                extraction=extraction,
            )
        finally:
            extraction.cleanup()

    def _persist_extraction(
        self,
        path: Path,
        *,
        source_type: str,
        content_hash: str,
        raw_bytes: int,
        extraction: ExtractionArtifact,
    ) -> IngestedDocument:
        document = self._repository.create_document(
            DocumentCreate(
                source_uri=path.as_uri(),
                source_type=source_type,
                title=path.stem,
                content_hash=content_hash,
                access_scope="internal",
                parser_version="isolated-local-file-v2",
                metadata={
                    "file_name": path.name,
                    "suffix": path.suffix.lower(),
                    "bytes": raw_bytes,
                    "page_count": extraction.page_count,
                    "extracted_characters": extraction.extracted_characters,
                    "extraction_peak_rss_bytes": extraction.peak_rss_bytes,
                    "extraction_memory_warning": extraction.memory_warning,
                    **extraction.dataset_metadata,
                },
            )
        )
        evidence_count = 0
        chunk_count = 0
        for page in _iter_extracted_pages(extraction.pages_path):
            evidence_hash = _sha256(
                f"{content_hash}:{page.page_number}:{page.text}".encode("utf-8")
            )
            evidence = self._repository.create_evidence_item(
                EvidenceItemCreate(
                    document_id=document.id,
                    source_uri=document.source_uri,
                    source_type=document.source_type,
                    title=document.title,
                    evidence_grade="source",
                    excerpt=_excerpt(
                        page.text,
                        preserve_layout=source_type == "csv",
                        max_chars=4000 if source_type == "csv" else 500,
                    ),
                    content_hash=evidence_hash,
                    access_scope=document.access_scope,
                    parser_version=document.parser_version,
                    page_or_section=page.section_label,
                    metadata={
                        "file_name": path.name,
                        "page_number": page.page_number,
                    },
                )
            )
            evidence_count += 1
            for chunk in chunk_text(
                page.text,
                chunk_size=self._chunk_size,
                overlap=self._overlap,
            ):
                self._repository.create_chunk(
                    ChunkCreate(
                        document_id=document.id,
                        evidence_item_id=evidence.id,
                        chunk_index=chunk_count,
                        text=chunk.text,
                        content_hash=_sha256(chunk.text.encode("utf-8")),
                        metadata={
                            "start_char": chunk.start_char,
                            "end_char": chunk.end_char,
                            "page_number": page.page_number,
                        },
                    )
                )
                chunk_count += 1
        return IngestedDocument(
            document_id=document.id,
            content_hash=content_hash,
            created=True,
            evidence_count=evidence_count,
            chunk_count=chunk_count,
        )


def _source_type_for_suffix(suffix: str) -> str:
    normalized = suffix.lower()
    if normalized == ".txt":
        return "text"
    if normalized == ".md":
        return "markdown"
    if normalized == ".pdf":
        return "pdf"
    if normalized == ".csv":
        return "csv"
    raise UnsupportedSourceType(f"Unsupported local file type: {suffix}")


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _excerpt(
    text: str,
    *,
    max_chars: int = 500,
    preserve_layout: bool = False,
) -> str:
    normalized = text.strip() if preserve_layout else " ".join(text.split())
    return normalized[:max_chars]


def _iter_extracted_pages(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            yield ExtractedPage(
                page_number=int(payload["page_number"]),
                section_label=str(payload["section_label"]),
                text=str(payload["text"]),
            )

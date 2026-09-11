from __future__ import annotations

from pathlib import Path
import shutil
from urllib.parse import unquote, urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from investment_agent.api.dependencies import get_db_session
from investment_agent.cloud import EventEnvelope
from investment_agent.ingestion import (
    DocumentResourceError,
    DocumentResourcePolicy,
    LocalFileIngestor,
    UnsupportedSourceType,
)
from investment_agent.repositories import DocumentRepository, ResearchHistoryRepository

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentIngestRequest(BaseModel):
    path: str = Field(min_length=1)


class DocumentIngestResponse(BaseModel):
    document_id: int
    content_hash: str
    created: bool
    evidence_count: int
    chunk_count: int


class DocumentSummary(BaseModel):
    id: int
    source_uri: str
    source_type: str
    title: str
    content_hash: str
    access_scope: str
    parser_version: str
    metadata: dict


class DocumentPurgeResponse(BaseModel):
    documents_deleted: int
    upload_files_deleted: int
    runs_deleted: int
    reports_deleted: int


@router.post(
    "/ingest",
    response_model=DocumentIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingest_document(
    request: DocumentIngestRequest,
    http_request: Request,
    session: Session = Depends(get_db_session),
) -> DocumentIngestResponse:
    return _ingest_path(
        Path(request.path),
        session=session,
        policy=_document_resource_policy(http_request),
    )


@router.post(
    "/upload",
    response_model=DocumentIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    request: Request,
    x_argus_filename: str = Header(alias="X-Argus-Filename"),
    session: Session = Depends(get_db_session),
) -> DocumentIngestResponse:
    policy = _document_resource_policy(request)
    upload_path = await _stream_uploaded_file(
        request=request,
        filename=unquote(x_argus_filename),
        policy=policy,
        upload_root=_managed_upload_root(request),
    )
    try:
        result = _ingest_path(upload_path, session=session, policy=policy)
    except HTTPException:
        _remove_managed_upload(
            upload_path,
            upload_root=_managed_upload_root(request),
        )
        raise
    if not result.created:
        _remove_managed_upload(
            upload_path,
            upload_root=_managed_upload_root(request),
        )
        return result

    artifact_uri = request.app.state.artifact_store.put_file(
        _raw_artifact_key(result.content_hash, upload_path.name),
        upload_path,
        content_type=request.headers.get("content-type", "application/octet-stream"),
    )
    request.app.state.event_publisher.publish(
        EventEnvelope(
            event_type="document.ingested.v1",
            aggregate_id=str(result.document_id),
            payload={
                "document_id": result.document_id,
                "content_hash": result.content_hash,
                "artifact_uri": artifact_uri,
            },
        )
    )
    return result


def _ingest_path(
    path: Path,
    *,
    session: Session,
    policy: DocumentResourcePolicy,
) -> DocumentIngestResponse:
    try:
        result = LocalFileIngestor(session, resource_policy=policy).ingest_path(path)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnsupportedSourceType as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="File is not valid UTF-8 text",
        ) from exc
    except DocumentResourceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.to_detail(),
        ) from exc
    except ValueError as exc:
        detail = str(exc)
        if detail.startswith("No extractable text found in "):
            detail = (
                "This PDF has no extractable text layer. It is probably a scanned or "
                "image-only PDF; run OCR first, then choose the searchable PDF again."
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail,
        ) from exc

    return DocumentIngestResponse(
        document_id=result.document_id,
        content_hash=result.content_hash,
        created=result.created,
        evidence_count=result.evidence_count,
        chunk_count=result.chunk_count,
    )


async def _stream_uploaded_file(
    *,
    request: Request,
    filename: str,
    policy: DocumentResourcePolicy,
    upload_root: Path,
) -> Path:
    original_name = Path(filename).name.strip()
    if not original_name:
        raise HTTPException(
            status_code=422,
            detail="Uploaded file name is required.",
        )

    upload_dir = upload_root / uuid4().hex
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / original_name
    content_length = request.headers.get("content-length")
    try:
        declared_bytes = int(content_length) if content_length else None
    except ValueError:
        declared_bytes = None
    if declared_bytes is not None and declared_bytes > policy.max_upload_bytes:
        _remove_managed_upload(target, upload_root=upload_root)
        raise HTTPException(
            status_code=413,
            detail=DocumentResourceError(
                "upload_too_large",
                "Upload stopped because the file exceeds the 25 MiB research-source limit.",
                stage="upload",
                observed=declared_bytes,
                limit=policy.max_upload_bytes,
                next_action="Split or compress the source file, then retry.",
                status_code=413,
            ).to_detail(),
        )
    observed = 0
    try:
        with target.open("xb") as handle:
            async for chunk in request.stream():
                observed += len(chunk)
                if observed > policy.max_upload_bytes:
                    raise DocumentResourceError(
                        "upload_too_large",
                        "Upload stopped because the received file exceeded the 25 MiB research-source limit.",
                        stage="upload",
                        observed=observed,
                        limit=policy.max_upload_bytes,
                        next_action="Split or compress the source file, then retry.",
                        status_code=413,
                    )
                handle.write(chunk)
        if observed == 0:
            raise DocumentResourceError(
                "empty_upload",
                "Uploaded file is empty.",
                stage="upload",
                observed=0,
                limit=policy.max_upload_bytes,
                next_action="Choose a non-empty research document.",
            )
        return target
    except DocumentResourceError as exc:
        _remove_managed_upload(target, upload_root=upload_root)
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


def _document_resource_policy(request: Request) -> DocumentResourcePolicy:
    settings = request.app.state.settings
    return DocumentResourcePolicy(
        max_upload_bytes=settings.document_upload_max_bytes,
        max_pdf_pages=settings.document_pdf_max_pages,
        max_extracted_characters=settings.document_extracted_text_max_characters,
        timeout_seconds=settings.document_extraction_timeout_seconds,
        warning_rss_bytes=settings.document_extraction_warning_rss_bytes,
        max_rss_bytes=settings.document_extraction_max_rss_bytes,
        poll_interval_seconds=settings.document_resource_poll_interval_ms / 1000,
        terminate_grace_seconds=settings.document_resource_terminate_grace_seconds,
        admission_memory_ratio=settings.document_admission_memory_ratio,
    )


@router.get("", response_model=list[DocumentSummary])
def list_documents(
    session: Session = Depends(get_db_session),
) -> list[DocumentSummary]:
    documents = DocumentRepository(session).list_documents()
    return [
        DocumentSummary(
            id=document.id,
            source_uri=document.source_uri,
            source_type=document.source_type,
            title=document.title,
            content_hash=document.content_hash,
            access_scope=document.access_scope,
            parser_version=document.parser_version,
            metadata=document.metadata_json,
        )
        for document in documents
    ]


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    request: Request,
    session: Session = Depends(get_db_session),
) -> None:
    repository = DocumentRepository(session)
    document = repository.get_document(document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Indexed source was not found.",
        )

    upload_root = _managed_upload_root(request)
    upload_path = _managed_upload_path(document.source_uri, upload_root=upload_root)
    if upload_path is not None:
        request.app.state.artifact_store.delete(
            _raw_artifact_key(document.content_hash, upload_path.name)
        )
        _remove_managed_upload(upload_path, upload_root=upload_root)

    ResearchHistoryRepository(session).purge_for_document(document_id)
    repository.delete_document(document_id)


@router.delete("", response_model=DocumentPurgeResponse)
def delete_all_documents(
    request: Request,
    session: Session = Depends(get_db_session),
) -> DocumentPurgeResponse:
    """Remove every indexed evidence source and its dependent research history."""

    repository = DocumentRepository(session)
    history_repository = ResearchHistoryRepository(session)
    documents = repository.list_documents()
    upload_root = _managed_upload_root(request)
    upload_files_before = _managed_upload_file_count(upload_root)
    run_ids: set[int] = set()
    report_ids: set[int] = set()

    for document in documents:
        upload_path = _managed_upload_path(
            document.source_uri,
            upload_root=upload_root,
        )
        if upload_path is not None:
            request.app.state.artifact_store.delete(
                _raw_artifact_key(document.content_hash, upload_path.name)
            )
            _remove_managed_upload(upload_path, upload_root=upload_root)

        purged = history_repository.purge_for_document(document.id)
        run_ids.update(purged.run_ids)
        report_ids.update(purged.report_ids)
        repository.delete_document(document.id)

    _clear_managed_upload_root(upload_root)
    return DocumentPurgeResponse(
        documents_deleted=len(documents),
        upload_files_deleted=upload_files_before,
        runs_deleted=len(run_ids),
        reports_deleted=len(report_ids),
    )


def _raw_artifact_key(content_hash: str, filename: str) -> str:
    return f"raw/{content_hash}/{filename}"


def _managed_upload_root(request: Request) -> Path:
    upload_root = Path(request.app.state.settings.document_upload_root).resolve()
    if upload_root.name != "uploads" or upload_root == Path(upload_root.anchor):
        raise RuntimeError(
            "ARGUS_DOCUMENT_UPLOAD_ROOT must identify a dedicated 'uploads' directory"
        )
    return upload_root


def _managed_upload_path(source_uri: str, *, upload_root: Path) -> Path | None:
    parsed = urlparse(source_uri)
    if parsed.scheme != "file":
        return None

    path = Path(unquote(parsed.path)).resolve()
    return path if path.is_relative_to(upload_root) else None


def _remove_managed_upload(path: Path, *, upload_root: Path) -> None:
    path = path.resolve()
    upload_root = upload_root.resolve()
    if not path.is_relative_to(upload_root):
        raise ValueError("Managed upload path must stay inside the upload root")
    path.unlink(missing_ok=True)
    parent = path.parent
    while parent != upload_root and parent.is_relative_to(upload_root):
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def _managed_upload_file_count(upload_root: Path) -> int:
    if not upload_root.exists():
        return 0
    return sum(1 for path in upload_root.rglob("*") if path.is_file())


def _clear_managed_upload_root(upload_root: Path) -> None:
    upload_root = upload_root.resolve()
    if not upload_root.exists():
        return
    for child in upload_root.iterdir():
        if child.is_symlink() or child.is_file():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            shutil.rmtree(child)

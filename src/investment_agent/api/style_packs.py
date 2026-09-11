from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, ValidationError
from pypdf.errors import PdfReadError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from investment_agent.api.dependencies import get_db_session
from investment_agent.method_documents import (
    MAX_METHOD_DOCUMENT_BYTES,
    MAX_METHOD_PANEL_DOCUMENTS,
    CompiledMethodDocument,
    compile_method_document,
)
from investment_agent.repositories.method_documents import (
    InvestmentMethodDocumentRepository,
)
from investment_agent.repositories import (
    InvestmentStylePackRepository,
    ResearchHistoryRepository,
    UserProfileRepository,
)
from investment_agent.style_packs import (
    BUILTIN_STYLE_BY_ID,
    BUILTIN_STYLE_PACKS,
    StylePackDefinition,
    normalize_style_pack_id,
)
from investment_agent.storage import UserProfile

router = APIRouter(prefix="/styles", tags=["investment styles"])
MAX_STYLE_PACK_BYTES = 64 * 1024
_METHOD_PACK_BLOCK = re.compile(
    r"```argus-method-pack\s*(\{.*?\})\s*```",
    flags=re.DOTALL | re.IGNORECASE,
)


class StylePackResponse(BaseModel):
    definition: StylePackDefinition
    builtin: bool


@router.get("/method-documents", response_model=list[CompiledMethodDocument])
def list_method_documents(
    session: Session = Depends(get_db_session),
) -> list[CompiledMethodDocument]:
    repository = InvestmentMethodDocumentRepository(session)
    return [repository.definition(record) for record in repository.list_all()]


@router.post(
    "/method-documents/upload",
    response_model=CompiledMethodDocument,
    status_code=status.HTTP_201_CREATED,
)
async def upload_method_document(
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session),
) -> CompiledMethodDocument:
    filename = str(file.filename or "").strip()
    raw = await file.read(MAX_METHOD_DOCUMENT_BYTES + 1)
    await file.close()
    try:
        compiled = compile_method_document(filename, raw)
    except (UnicodeDecodeError, PdfReadError, ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid expert method add-on: {exc}",
        ) from exc
    repository = InvestmentMethodDocumentRepository(session)
    return repository.definition(repository.save(compiled))


@router.delete("/method-documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_method_document(
    document_id: int,
    session: Session = Depends(get_db_session),
) -> Response:
    repository = InvestmentMethodDocumentRepository(session)
    document = repository.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Expert method add-on not found.")
    ResearchHistoryRepository(session).purge_for_method_document(
        document_id,
        content_hash=document.content_hash,
    )
    session.execute(
        update(UserProfile)
        .where(UserProfile.preferred_method_document_id == document_id)
        .values(preferred_method_document_id=None)
    )
    for profile in session.scalars(select(UserProfile)):
        profile.preferred_method_document_ids_json = [
            value
            for value in (profile.preferred_method_document_ids_json or [])
            if value != document_id
        ]
    repository.delete(document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=list[StylePackResponse])
def list_style_packs(
    session: Session = Depends(get_db_session),
) -> list[StylePackResponse]:
    custom = [
        StylePackResponse(
            definition=StylePackDefinition.model_validate(record.definition_json),
            builtin=False,
        )
        for record in InvestmentStylePackRepository(session).list_custom()
    ]
    return [
        *(StylePackResponse(definition=pack, builtin=True) for pack in BUILTIN_STYLE_PACKS),
        *custom,
    ]


@router.post(
    "/upload",
    response_model=StylePackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_style_pack(
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session),
) -> StylePackResponse:
    filename = str(file.filename or "").strip()
    if not filename.lower().endswith((".json", ".md", ".markdown")):
        raise HTTPException(
            status_code=422,
            detail="Method Pack must be JSON or Markdown with an argus-method-pack block.",
        )
    raw = await file.read(MAX_STYLE_PACK_BYTES + 1)
    await file.close()
    if len(raw) > MAX_STYLE_PACK_BYTES:
        raise HTTPException(status_code=413, detail="Method Pack exceeds 64 KB.")
    try:
        definition = StylePackDefinition.model_validate(
            _parse_method_pack_payload(filename, raw)
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid declarative Method Pack: {exc}",
        ) from exc
    if definition.id in BUILTIN_STYLE_BY_ID:
        raise HTTPException(
            status_code=409,
            detail="A custom Style Pack cannot replace a built-in Style Pack.",
        )
    InvestmentStylePackRepository(session).save(definition)
    return StylePackResponse(definition=definition, builtin=False)


@router.delete("/{style_pack_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_style_pack(
    style_pack_id: str,
    session: Session = Depends(get_db_session),
) -> Response:
    normalized = normalize_style_pack_id(style_pack_id)
    if normalized in BUILTIN_STYLE_BY_ID:
        raise HTTPException(status_code=409, detail="Built-in Style Packs cannot be deleted.")
    if not InvestmentStylePackRepository(session).delete(normalized):
        raise HTTPException(status_code=404, detail="Style Pack not found.")
    profile = UserProfileRepository(session).get_active_profile()
    if profile is not None and normalize_style_pack_id(profile.preferred_style) == normalized:
        profile.preferred_style = "strategic_index"
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def resolve_style_pack(
    session: Session,
    style_pack_id: str | None,
) -> StylePackDefinition:
    normalized = normalize_style_pack_id(style_pack_id)
    builtin = BUILTIN_STYLE_BY_ID.get(normalized)
    if builtin is not None:
        return builtin
    record = InvestmentStylePackRepository(session).get_by_slug(normalized)
    if record is None:
        raise HTTPException(status_code=422, detail=f"Unknown Style Pack: {normalized}")
    return StylePackDefinition.model_validate(record.definition_json)


def resolve_method_document(
    session: Session,
    document_id: int | None,
) -> CompiledMethodDocument | None:
    if document_id is None:
        return None
    repository = InvestmentMethodDocumentRepository(session)
    record = repository.get(document_id)
    if record is None:
        raise HTTPException(status_code=422, detail="Unknown expert method add-on.")
    return repository.definition(record)


def resolve_method_documents(
    session: Session,
    document_ids: list[int] | tuple[int, ...] | None,
) -> tuple[CompiledMethodDocument, ...]:
    unique_ids = list(dict.fromkeys(document_ids or []))
    if len(unique_ids) > MAX_METHOD_PANEL_DOCUMENTS:
        raise HTTPException(
            status_code=422,
            detail=f"Choose at most {MAX_METHOD_PANEL_DOCUMENTS} expert method add-ons for one research panel.",
        )
    return tuple(
        document
        for document_id in unique_ids
        if (document := resolve_method_document(session, document_id)) is not None
    )


def _parse_method_pack_payload(filename: str, raw: bytes) -> dict[str, Any]:
    if filename.lower().endswith(".json"):
        payload = json.loads(raw)
    else:
        markdown = raw.decode("utf-8")
        matches = _METHOD_PACK_BLOCK.findall(markdown)
        if not matches:
            raise ValueError(
                "Markdown Method Packs must contain one fenced "
                "```argus-method-pack JSON block. Free-form SKILL.md instructions "
                "are never executed."
            )
        if len(matches) != 1:
            raise ValueError("Markdown Method Packs must contain exactly one data block.")
        payload = json.loads(matches[0])
    if not isinstance(payload, dict):
        raise ValueError("Method Pack root must be a JSON object.")
    return payload

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class EvidenceRelation(StrEnum):
    SUPPORTS = "supports"
    OPPOSES = "opposes"


class EvidenceItem(BaseModel):
    evidence_id: str
    document_id: str
    source_uri: str
    source_type: str
    title: str
    publisher: str | None = None
    page_or_section: str | None = None
    publication_date: date | None = None
    data_as_of_date: date | None = None
    ingested_at: datetime
    evidence_grade: str
    excerpt: str
    content_hash: str
    access_scope: str
    parser_version: str


class Claim(BaseModel):
    claim_id: str
    run_id: str
    claim_text: str
    evidence_ids: list[str] = Field(min_length=1)
    relations: dict[str, EvidenceRelation]
    confidence: float = Field(ge=0.0, le=1.0)
    skill_version: str
    model_profile: str
    created_at: datetime

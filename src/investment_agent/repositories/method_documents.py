from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from investment_agent.method_documents import CompiledMethodDocument
from investment_agent.storage.models import InvestmentMethodDocument


class InvestmentMethodDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self) -> list[InvestmentMethodDocument]:
        return list(
            self._session.scalars(
                select(InvestmentMethodDocument).order_by(
                    InvestmentMethodDocument.name.asc(),
                    InvestmentMethodDocument.id.asc(),
                )
            )
        )

    def get(self, document_id: int) -> InvestmentMethodDocument | None:
        return self._session.get(InvestmentMethodDocument, document_id)

    def get_by_hash(self, content_hash: str) -> InvestmentMethodDocument | None:
        return self._session.scalar(
            select(InvestmentMethodDocument).where(
                InvestmentMethodDocument.content_hash == content_hash
            )
        )

    def save(self, compiled: CompiledMethodDocument) -> InvestmentMethodDocument:
        existing = self.get_by_hash(compiled.content_hash)
        if existing is not None:
            return existing
        record = InvestmentMethodDocument(
            name=compiled.name,
            file_name=compiled.file_name,
            source_type=compiled.source_type,
            content_hash=compiled.content_hash,
            character_count=compiled.character_count,
            checklist_json=list(compiled.checklist_items),
            detected_lenses_json=list(compiled.detected_lenses),
            focus_terms_json=list(compiled.focus_terms),
            warnings_json=list(compiled.warnings),
        )
        self._session.add(record)
        self._session.flush()
        return record

    def delete(self, document_id: int) -> bool:
        record = self.get(document_id)
        if record is None:
            return False
        self._session.delete(record)
        self._session.flush()
        return True

    @staticmethod
    def definition(record: InvestmentMethodDocument) -> CompiledMethodDocument:
        return CompiledMethodDocument(
            id=record.id,
            name=record.name,
            file_name=record.file_name,
            source_type=record.source_type,
            content_hash=record.content_hash,
            character_count=record.character_count,
            checklist_items=list(record.checklist_json),
            detected_lenses=list(record.detected_lenses_json),
            focus_terms=list(record.focus_terms_json),
            warnings=list(record.warnings_json),
        )

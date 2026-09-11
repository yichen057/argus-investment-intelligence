from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from investment_agent.storage.models import InvestmentStylePack
from investment_agent.style_packs import StylePackDefinition


class InvestmentStylePackRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_custom(self) -> list[InvestmentStylePack]:
        return list(
            self._session.scalars(
                select(InvestmentStylePack).order_by(InvestmentStylePack.name.asc())
            )
        )

    def get_by_slug(self, slug: str) -> InvestmentStylePack | None:
        return self._session.scalar(
            select(InvestmentStylePack).where(InvestmentStylePack.slug == slug)
        )

    def save(self, definition: StylePackDefinition) -> InvestmentStylePack:
        record = self.get_by_slug(definition.id)
        if record is None:
            record = InvestmentStylePack(
                slug=definition.id,
                name=definition.name,
                definition_json=definition.model_dump(mode="json"),
            )
            self._session.add(record)
        else:
            record.name = definition.name
            record.definition_json = definition.model_dump(mode="json")
        self._session.flush()
        return record

    def delete(self, slug: str) -> bool:
        record = self.get_by_slug(slug)
        if record is None:
            return False
        self._session.delete(record)
        self._session.flush()
        return True

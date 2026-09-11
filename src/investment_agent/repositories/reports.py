from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from investment_agent.storage.models import Report


@dataclass(frozen=True)
class ReportCreate:
    title: str
    report_type: str
    status: str
    report_json: dict[str, Any]
    rendered_html: str


class ReportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_report(self, payload: ReportCreate) -> Report:
        report = Report(
            title=payload.title,
            report_type=payload.report_type,
            status=payload.status,
            report_json=payload.report_json,
            rendered_html=payload.rendered_html,
        )
        self._session.add(report)
        self._session.flush()
        return report

    def get_report(self, report_id: int) -> Report | None:
        return self._session.get(Report, report_id)

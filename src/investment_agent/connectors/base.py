from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class SourceRef:
    connector_id: str
    external_id: str
    source_uri: str


@dataclass(frozen=True)
class RawSource:
    ref: SourceRef
    content: bytes
    media_type: str
    observed_at: datetime
    metadata: dict[str, str]


class SourceConnector(Protocol):
    def discover(self, cursor: str | None = None) -> tuple[list[SourceRef], str | None]:
        ...

    def fetch(self, ref: SourceRef) -> RawSource:
        ...

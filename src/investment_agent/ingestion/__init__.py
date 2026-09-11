"""Local document ingestion."""

from investment_agent.ingestion.local_files import (
    IngestedDocument,
    LocalFileIngestor,
    UnsupportedSourceType,
)
from investment_agent.ingestion.resources import (
    DocumentResourceError,
    DocumentResourcePolicy,
)

__all__ = [
    "DocumentResourceError",
    "DocumentResourcePolicy",
    "IngestedDocument",
    "LocalFileIngestor",
    "UnsupportedSourceType",
]

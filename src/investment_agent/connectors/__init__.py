"""Source connector interfaces."""

from investment_agent.connectors.base import RawSource, SourceConnector, SourceRef
from investment_agent.connectors.gmail import GmailFilter

__all__ = ["GmailFilter", "RawSource", "SourceConnector", "SourceRef"]

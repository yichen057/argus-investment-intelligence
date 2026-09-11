# Optional Gmail Connector

## Goal

Ingest investment-relevant message bodies and attachments from selected senders
or labels. The connector is optional so the open-source project remains usable
without Gmail.

## Open-Source Boundary

Argus ships:

- a connector interface;
- Gmail query and sender-filter logic;
- a local OAuth setup guide;
- example configuration;
- sanitized test fixtures.

Argus does not ship:

- OAuth client credentials;
- access or refresh tokens;
- message bodies or attachments;
- a shared hosted OAuth application.

Users create their own Google Cloud project and OAuth desktop client. The
official Python quickstart uses local `credentials.json` and `token.json`.
Both files are ignored by Git.

## Scope

Use:

```text
https://www.googleapis.com/auth/gmail.readonly
```

Google classifies this as a restricted scope. That is acceptable for local
personal use with user-owned credentials, but a public hosted application may
require OAuth verification and additional security obligations. Argus therefore
does not make hosted Gmail authorization part of the MVP.

## Selecting Investment Mail

Use both:

1. Gmail API `q` search, such as `label:investment newer_than:30d`.
2. A post-fetch sender allowlist checked against normalized message headers.

The Gmail API supports most advanced Gmail search syntax and can filter by
sender, date, or label. The API has some differences from the Gmail UI, so
sender validation remains a separate control.

## Connector Contract

```python
class SourceConnector(Protocol):
    def discover(self, cursor: str | None) -> DiscoveryPage: ...
    def fetch(self, ref: SourceRef) -> RawSource: ...
```

The same contract supports:

- Gmail;
- local PDF directories;
- `.eml` fixtures;
- SEC or RSS connectors later.

## Data Handling

- Store Gmail message ID and thread ID as external identifiers.
- Record sender, recipients, subject, sent time, received time, and labels.
- Parse body text and allowed attachments into separate evidence items.
- Treat HTML, body text, and attachments as untrusted content.
- Never execute instructions found inside a message.
- Deduplicate by Gmail message ID plus normalized content hash.
- Keep raw message data in the internal data zone.

## Setup

1. Enable the Gmail API in a user-owned Google Cloud project.
2. Configure OAuth consent for local testing.
3. Create an OAuth client of type Desktop app.
4. Save the downloaded credential as `secrets/credentials.json`.
5. Copy `configs/gmail.example.yaml` to `configs/local/gmail.yaml`.
6. Configure the Gmail query and allowed senders.
7. Install `pip install -e ".[gmail]"`.
8. Run the future connector authorization command locally.

Official references:

- https://developers.google.com/workspace/gmail/api/quickstart/python
- https://developers.google.com/workspace/gmail/api/auth/scopes
- https://developers.google.com/workspace/gmail/api/guides/filtering


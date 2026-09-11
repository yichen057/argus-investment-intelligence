from dataclasses import dataclass


GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


@dataclass(frozen=True)
class GmailFilter:
    query: str = ""
    allowed_senders: tuple[str, ...] = ()
    after_epoch: int | None = None

    def api_query(self) -> str:
        parts: list[str] = []
        if self.query.strip():
            parts.append(self.query.strip())
        if self.allowed_senders:
            sender_terms = " ".join(
                f"from:{sender.strip().lower()}"
                for sender in self.allowed_senders
                if sender.strip()
            )
            if sender_terms:
                parts.append(
                    sender_terms
                    if len(self.allowed_senders) == 1
                    else "{" + sender_terms + "}"
                )
        if self.after_epoch is not None:
            parts.append(f"after:{self.after_epoch}")
        return " ".join(parts)

    def sender_allowed(self, sender: str) -> bool:
        if not self.allowed_senders:
            return True
        normalized = sender.strip().lower()
        return normalized in {
            allowed.strip().lower() for allowed in self.allowed_senders
        }

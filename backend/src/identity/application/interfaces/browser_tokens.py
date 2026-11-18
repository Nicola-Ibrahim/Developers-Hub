from datetime import datetime
from typing import Protocol


class BrowserSessionTokenIssuer(Protocol):
    def issue(self, subject: str, issued_at: datetime, expires_at: datetime) -> str: ...


class BrowserSessionTokenVerifier(Protocol):
    def verify(self, token: str) -> bool: ...

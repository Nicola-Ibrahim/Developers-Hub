from datetime import datetime
from typing import Protocol


class SessionTokenIssuer(Protocol):
    def issue(self, subject: str, issued_at: datetime, expires_at: datetime) -> str: ...


class SessionTokenVerifier(Protocol):
    def verify(self, token: str) -> bool: ...

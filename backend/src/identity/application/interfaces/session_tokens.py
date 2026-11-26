from abc import ABC, abstractmethod
from datetime import datetime


class SessionTokenIssuer(ABC):
    @abstractmethod
    def issue(self, subject: str, issued_at: datetime, expires_at: datetime) -> str: ...


class SessionTokenVerifier(ABC):
    @abstractmethod
    def verify(self, token: str) -> bool: ...

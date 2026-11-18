from typing import Protocol


class LoginCredentialVerifier(Protocol):
    async def verify(self, password: str, encoded: str | None) -> bool: ...

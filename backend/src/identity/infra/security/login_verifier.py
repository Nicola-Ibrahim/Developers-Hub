"""Off-thread password verification with a precomputed dummy credential."""

import asyncio

from identity.application.interfaces.security import PasswordHasher


class LoginCredentialVerifier:
    def __init__(self, passwords: PasswordHasher) -> None:
        self._passwords = passwords
        self._dummy_hash = passwords.hash("devops-hub-dummy-password-value")

    async def verify(self, password: str, encoded: str | None) -> bool:
        return await asyncio.to_thread(
            self._passwords.verify,
            password,
            encoded if encoded is not None else self._dummy_hash,
        )

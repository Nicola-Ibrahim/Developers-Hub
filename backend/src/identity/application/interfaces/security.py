from typing import Protocol

__all__ = [
    "PasswordHasher",
    "TokenGenerator",
    "TokenHasher",
]


class TokenHasher(Protocol):
    def digest(self, token: str) -> str: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, encoded: str | None) -> bool: ...

    def needs_rehash(self, encoded: str) -> bool: ...


class TokenGenerator(Protocol):
    def generate(self) -> str: ...

from abc import ABC, abstractmethod

__all__ = [
    "PasswordHasher",
    "TokenGenerator",
    "TokenHasher",
]


class TokenHasher(ABC):
    @abstractmethod
    def digest(self, token: str) -> str: ...


class PasswordHasher(ABC):
    @abstractmethod
    def hash(self, password: str) -> str: ...

    @abstractmethod
    def verify(self, password: str, encoded: str | None) -> bool: ...

    @abstractmethod
    def needs_rehash(self, encoded: str) -> bool: ...


class TokenGenerator(ABC):
    @abstractmethod
    def generate(self) -> str: ...

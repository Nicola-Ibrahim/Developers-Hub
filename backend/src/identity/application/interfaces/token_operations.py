"""Transaction port for API token authentication and revocation."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TypeVar

from identity.domain.interfaces.api_token_repository import ApiTokenRepository

T = TypeVar("T")


class ApiTokenTransaction(ABC):
    @abstractmethod
    async def run(self, action: Callable[[ApiTokenRepository], Awaitable[T]]) -> T: ...

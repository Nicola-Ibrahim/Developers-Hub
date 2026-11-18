"""Transaction port for API token authentication and revocation."""

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

from identity.domain.interfaces.api_token_repository import ApiTokenRepository

T = TypeVar("T")


class ApiTokenTransaction(Protocol):
    async def run(self, action: Callable[[ApiTokenRepository], Awaitable[T]]) -> T: ...

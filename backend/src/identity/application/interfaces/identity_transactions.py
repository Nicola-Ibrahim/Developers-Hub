"""Transaction boundary for browser identity application workflows."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TypeVar

from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository

T = TypeVar("T")


class IdentityTransaction(ABC):
    @abstractmethod
    async def run(
        self, action: Callable[[UserRepository, SessionRepository], Awaitable[T]]
    ) -> T: ...

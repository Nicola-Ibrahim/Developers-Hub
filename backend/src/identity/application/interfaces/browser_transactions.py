"""Transaction boundary for browser identity application workflows."""

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

from identity.domain.interfaces.password_setup_repository import PasswordSetupRepository
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository

T = TypeVar("T")


class BrowserRepository(
    SessionRepository,
    UserRepository,
    PasswordSetupRepository,
    Protocol,
):
    """Existing identity repository capabilities available inside a transaction."""


class BrowserTransaction(Protocol):
    async def run(self, action: Callable[[BrowserRepository], Awaitable[T]]) -> T: ...

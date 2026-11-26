"""Public dispatch contract for identity commands and queries."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TypeVar

from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.records import SessionPrincipal
from shared.dispatch import Command, Query

ResultT = TypeVar("ResultT")
ActionPrecondition = Callable[
    [SessionRepository, ApiTokenRepository | None], Awaitable[SessionPrincipal]
]


class IdentityModule(ABC):
    @abstractmethod
    async def execute(self, command: Command[ResultT]) -> ResultT: ...

    @abstractmethod
    async def query(self, query: Query[ResultT]) -> ResultT: ...

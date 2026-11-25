"""Public dispatch contract for identity commands and queries."""

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.records import SessionPrincipal
from shared.dispatch import Command, Query

ResultT = TypeVar("ResultT")
ActionPrecondition = Callable[
    [SessionRepository, ApiTokenRepository | None], Awaitable[SessionPrincipal]
]


class IdentityModule(Protocol):
    async def execute(self, command: Command[ResultT]) -> ResultT: ...

    async def execute_with_precondition(
        self,
        command: Command[ResultT],
        precondition: ActionPrecondition,
    ) -> ResultT: ...

    async def query(self, query: Query[ResultT]) -> ResultT: ...

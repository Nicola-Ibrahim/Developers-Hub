"""Identity token operations with operation-scoped transaction completion."""

from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.application.interfaces.token_operations import ApiTokenTransaction
from identity.application.shared.errors import IdentityUnavailable
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from shared.infra.persistence.unit_of_work import DatabaseUnavailable, SqlAlchemyUnitOfWork

T = TypeVar("T")


class SqlAlchemyApiTokenTransaction(ApiTokenTransaction):
    """Provide a short Identity transaction for application token operations."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        repository_factory: Callable[[AsyncSession], ApiTokenRepository],
    ) -> None:
        self.sessions = sessions
        self.repository_factory = repository_factory

    async def run(self, action: Callable[[ApiTokenRepository], Awaitable[T]]) -> T:
        try:
            session = self.sessions()
            return await SqlAlchemyUnitOfWork(session).run(
                lambda: action(self.repository_factory(session)), lambda value: value
            )
        except DatabaseUnavailable as error:
            raise IdentityUnavailable() from error

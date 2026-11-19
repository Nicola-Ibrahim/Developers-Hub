"""Short transaction adapter for Identity application workflows."""

from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.application.interfaces.browser_transactions import (
    BrowserRepository,
    BrowserTransaction,
)
from identity.application.shared.errors import IdentityUnavailable
from identity.infra.persistence.repositories.accounts_sessions import SQLAlchemyIdentityRepository
from shared.infra.persistence.unit_of_work import DatabaseUnavailable, SqlAlchemyUnitOfWork

T = TypeVar("T")


class SqlAlchemyIdentityTransaction(BrowserTransaction):
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        repository_factory: Callable[[AsyncSession], SQLAlchemyIdentityRepository],
    ) -> None:
        self.sessions = sessions
        self.repository_factory = repository_factory

    async def run(self, action: Callable[[BrowserRepository], Awaitable[T]]) -> T:
        try:
            session = self.sessions()
            return await SqlAlchemyUnitOfWork(session).run(
                lambda: action(self.repository_factory(session)), lambda result: result
            )
        except DatabaseUnavailable as error:
            raise IdentityUnavailable() from error

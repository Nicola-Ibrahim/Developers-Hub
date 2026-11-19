"""Short transaction adapter for Identity application workflows."""

from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.application.interfaces.browser_transactions import BrowserTransaction
from identity.application.shared.errors import IdentityUnavailable
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository
from shared.infra.persistence.unit_of_work import DatabaseUnavailable, SqlAlchemyUnitOfWork

T = TypeVar("T")


class SqlAlchemyIdentityTransaction(BrowserTransaction):
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        repository_factory: Callable[[AsyncSession], tuple[UserRepository, SessionRepository]],
    ) -> None:
        self.sessions = sessions
        self.repository_factory = repository_factory

    async def run(self, action: Callable[[UserRepository, SessionRepository], Awaitable[T]]) -> T:
        try:
            session = self.sessions()
            return await SqlAlchemyUnitOfWork(session).run(
                lambda: action(*self.repository_factory(session)), lambda result: result
            )
        except DatabaseUnavailable as error:
            raise IdentityUnavailable() from error

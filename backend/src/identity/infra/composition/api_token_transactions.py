"""Identity token operations with operation-scoped transaction completion."""

from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.application.api_tokens.issue_api_token.command import IssueApiTokenCommand
from identity.application.api_tokens.issue_api_token.handler import IssueApiTokenHandler
from identity.application.api_tokens.issue_api_token.result import PreparedApiToken
from identity.application.interfaces.security import (
    CredentialDelivery,
    CredentialReceipt,
)
from identity.application.interfaces.token_operations import ApiTokenTransaction
from identity.application.shared.errors import IdentityUnavailable
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.infra.persistence.repositories.api_tokens import SQLAlchemyApiTokenRepository
from shared.infra.persistence.unit_of_work import (
    DatabaseUnavailable,
    SqlAlchemyUnitOfWork,
)

T = TypeVar("T")


class SqlAlchemyApiTokenTransaction(ApiTokenTransaction):
    """Provide a short Identity transaction for application token operations."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def run(self, action: Callable[[ApiTokenRepository], Awaitable[T]]) -> T:
        try:
            session = self.sessions()
            return await SqlAlchemyUnitOfWork(session).run(
                lambda: action(SQLAlchemyApiTokenRepository(session)), lambda value: value
            )
        except DatabaseUnavailable as error:
            raise IdentityUnavailable() from error


class IssueApiTokenToFile:
    def __init__(self, inner: IssueApiTokenHandler, unit: SqlAlchemyUnitOfWork) -> None:
        self.inner = inner
        self.unit = unit

    async def execute(self, command: IssueApiTokenCommand, delivery: CredentialDelivery) -> UUID:
        receipt: CredentialReceipt | None = None

        def deliver(prepared: PreparedApiToken) -> UUID:
            nonlocal receipt
            receipt = delivery.write_new(prepared.secret)
            return prepared.token_id

        try:
            return await self.unit.run(lambda: self.inner.execute(command), deliver)
        except BaseException as primary:
            if receipt is not None and not self.unit.committed:
                try:
                    receipt.remove_owned()
                except BaseException:
                    primary.add_note(
                        "Credential cleanup failed; the original failure was preserved."
                    )
            if isinstance(primary, DatabaseUnavailable):
                raise IdentityUnavailable() from primary
            raise

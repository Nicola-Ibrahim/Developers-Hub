"""Per-dispatch Identity bindings isolated to Dishka's ACTION component."""

from typing import Annotated

from dishka import FromComponent, Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.application.authentication.logout.handler import LogoutHandler
from identity.application.interfaces.security import TokenHasher
from identity.application.sessions.revoke_all_sessions.handler import RevokeAllSessionsHandler
from identity.application.sessions.revoke_session.handler import RevokeSessionHandler
from identity.infra.composition.session_revocation_unit_of_work import (
    IdentitySessionRevocationUnitOfWork,
)
from identity.infra.persistence.repositories.accounts_sessions import SQLAlchemyIdentityRepository
from identity.infra.persistence.repositories.session_revocation import (
    SQLAlchemySessionRevocationRepository,
)
from shared.infra.clock import Clock
from shared.infra.persistence.unit_of_work import SqlAlchemyUnitOfWork
from shared.infra.settings import Settings


class IdentityActionProvider(Provider):
    """Create one session and all session-bound Identity adapters per dispatch."""

    @provide(scope=Scope.ACTION)
    def session(
        self,
        sessions: Annotated[async_sessionmaker[AsyncSession], FromComponent("")],
    ) -> AsyncSession:
        return sessions()

    unit_of_work = provide(SqlAlchemyUnitOfWork, scope=Scope.ACTION)

    @provide(scope=Scope.ACTION)
    def session_revocation_unit_of_work(
        self, unit: SqlAlchemyUnitOfWork
    ) -> IdentitySessionRevocationUnitOfWork:
        return IdentitySessionRevocationUnitOfWork(unit)

    @provide(scope=Scope.ACTION)
    def identity_repository(self, session: AsyncSession) -> SQLAlchemyIdentityRepository:
        # These actions do not need the optional Platform access rules used by
        # account deactivation; keep their session dependency local and explicit.
        return SQLAlchemyIdentityRepository(session)

    revocation_repository = provide(SQLAlchemySessionRevocationRepository, scope=Scope.ACTION)

    @provide(scope=Scope.ACTION)
    def logout_handler(
        self,
        repository: SQLAlchemyIdentityRepository,
        unit: IdentitySessionRevocationUnitOfWork,
        clock: Annotated[Clock, FromComponent("")],
        hasher: Annotated[TokenHasher, FromComponent("")],
        settings: Annotated[Settings, FromComponent("")],
    ) -> LogoutHandler:
        return LogoutHandler(
            repository,
            repository,
            unit,
            clock,
            hasher.digest,
            settings.browser_allowed_origins,
        )

    @provide(scope=Scope.ACTION)
    def revoke_all_sessions_handler(
        self,
        repository: SQLAlchemyIdentityRepository,
        unit: IdentitySessionRevocationUnitOfWork,
        clock: Annotated[Clock, FromComponent("")],
        hasher: Annotated[TokenHasher, FromComponent("")],
        settings: Annotated[Settings, FromComponent("")],
    ) -> RevokeAllSessionsHandler:
        return RevokeAllSessionsHandler(
            repository,
            repository,
            unit,
            clock,
            hasher.digest,
            settings.browser_allowed_origins,
        )

    @provide(scope=Scope.ACTION)
    def revoke_session_handler(
        self,
        repository: SQLAlchemyIdentityRepository,
        revocations: SQLAlchemySessionRevocationRepository,
        unit: IdentitySessionRevocationUnitOfWork,
        clock: Annotated[Clock, FromComponent("")],
        hasher: Annotated[TokenHasher, FromComponent("")],
        settings: Annotated[Settings, FromComponent("")],
    ) -> RevokeSessionHandler:
        return RevokeSessionHandler(
            repository,
            revocations,
            unit,
            clock,
            hasher.digest,
            settings.browser_allowed_origins,
        )

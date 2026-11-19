"""Per-dispatch Identity bindings isolated to Dishka's ACTION component."""

from typing import Annotated

from dishka import FromComponent, Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.application.authentication.authenticate_session.handler import (
    AuthenticateSessionHandler,
)
from identity.application.authentication.logout.handler import LogoutHandler
from identity.application.interfaces.security import TokenGenerator, TokenHasher
from identity.application.sessions.list_sessions.handler import ListSessionsHandler
from identity.application.sessions.revoke_all_sessions.handler import RevokeAllSessionsHandler
from identity.application.sessions.revoke_session.handler import RevokeSessionHandler
from identity.application.sessions.rotate_csrf.handler import RotateCsrfHandler
from identity.application.sessions.select_active_project.handler import SelectActiveProjectHandler
from identity.domain.interfaces.project_access import IdentityProjectAccess
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository
from identity.infra.persistence.repositories.sessions import SQLAlchemySessionRepository
from identity.infra.persistence.repositories.users import SQLAlchemyUserRepository
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
    def user_repository(
        self, session: AsyncSession, project_access: IdentityProjectAccess
    ) -> UserRepository:
        return SQLAlchemyUserRepository(session, project_access)

    @provide(scope=Scope.ACTION, provides=SessionRepository)
    def session_repository(
        self,
        session: AsyncSession,
        users: UserRepository,
        project_access: IdentityProjectAccess,
    ) -> SessionRepository:
        return SQLAlchemySessionRepository(session, users, project_access)

    @provide(scope=Scope.ACTION)
    def logout_handler(
        self,
        repository: SessionRepository,
        clock: Annotated[Clock, FromComponent("")],
        hasher: Annotated[TokenHasher, FromComponent("")],
        settings: Annotated[Settings, FromComponent("")],
    ) -> LogoutHandler:
        return LogoutHandler(repository, clock, hasher.digest, settings.browser_allowed_origins)

    @provide(scope=Scope.ACTION)
    def revoke_all_sessions_handler(
        self,
        repository: SessionRepository,
        clock: Annotated[Clock, FromComponent("")],
        hasher: Annotated[TokenHasher, FromComponent("")],
        settings: Annotated[Settings, FromComponent("")],
    ) -> RevokeAllSessionsHandler:
        return RevokeAllSessionsHandler(
            repository, clock, hasher.digest, settings.browser_allowed_origins
        )

    @provide(scope=Scope.ACTION)
    def revoke_session_handler(
        self,
        repository: SessionRepository,
        clock: Annotated[Clock, FromComponent("")],
        hasher: Annotated[TokenHasher, FromComponent("")],
        settings: Annotated[Settings, FromComponent("")],
    ) -> RevokeSessionHandler:
        return RevokeSessionHandler(
            repository, clock, hasher.digest, settings.browser_allowed_origins
        )

    @provide(scope=Scope.ACTION)
    def authenticate_session_handler(
        self,
        repository: SessionRepository,
        clock: Annotated[Clock, FromComponent("")],
        hasher: Annotated[TokenHasher, FromComponent("")],
    ) -> AuthenticateSessionHandler:
        return AuthenticateSessionHandler(repository, clock, hasher.digest)

    @provide(scope=Scope.ACTION)
    def list_sessions_handler(
        self,
        repository: SessionRepository,
        clock: Annotated[Clock, FromComponent("")],
        hasher: Annotated[TokenHasher, FromComponent("")],
    ) -> ListSessionsHandler:
        return ListSessionsHandler(repository, clock, hasher.digest)

    @provide(scope=Scope.ACTION)
    def rotate_csrf_handler(
        self,
        repository: SessionRepository,
        clock: Annotated[Clock, FromComponent("")],
        hasher: Annotated[TokenHasher, FromComponent("")],
        generator: Annotated[TokenGenerator, FromComponent("")],
    ) -> RotateCsrfHandler:
        return RotateCsrfHandler(repository, clock, hasher.digest, generator.generate)

    @provide(scope=Scope.ACTION)
    def select_active_project_handler(
        self,
        repository: SessionRepository,
        clock: Annotated[Clock, FromComponent("")],
        hasher: Annotated[TokenHasher, FromComponent("")],
        generator: Annotated[TokenGenerator, FromComponent("")],
        settings: Annotated[Settings, FromComponent("")],
    ) -> SelectActiveProjectHandler:
        return SelectActiveProjectHandler(
            repository, clock, hasher.digest, generator.generate, settings.browser_allowed_origins
        )

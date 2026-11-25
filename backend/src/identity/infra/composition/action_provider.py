"""Per-dispatch Identity bindings isolated to Dishka's ACTION component."""

from typing import Annotated

from dishka import FromComponent, Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.application.api_tokens.manage_personal_tokens import (
    CreatePersonalTokenHandler,
    PersonalTokenQueryHandler,
    RevokePersonalTokenHandler,
    RotatePersonalTokenHandler,
)
from identity.application.authentication.authenticate_session.handler import (
    AuthenticateSessionHandler,
)
from identity.application.authentication.logout.handler import LogoutHandler
from identity.application.interfaces.security import TokenGenerator, TokenHasher
from identity.application.profile.handlers import (
    ReadProfileHandler,
    SecurityHistoryHandler,
    UpdateProfileHandler,
)
from identity.application.sessions.list_sessions.handler import ListSessionsHandler
from identity.application.sessions.revoke_all_sessions.handler import RevokeAllSessionsHandler
from identity.application.sessions.revoke_session.handler import RevokeSessionHandler
from identity.application.sessions.rotate_csrf.handler import RotateCsrfHandler
from identity.application.sessions.select_active_project.handler import SelectActiveProjectHandler
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.domain.interfaces.project_access import IdentityProjectAccess
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository
from identity.infra.composition.providers import IdentityTokenScopePolicy
from identity.infra.persistence.repositories.sessions import SQLAlchemySessionRepository
from identity.infra.persistence.repositories.users import SQLAlchemyUserRepository
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
    def list_personal_tokens_handler(
        self,
        tokens: ApiTokenRepository,
    ) -> PersonalTokenQueryHandler:
        return PersonalTokenQueryHandler(tokens)

    @provide(scope=Scope.ACTION)
    def revoke_personal_token_handler(
        self,
        tokens: ApiTokenRepository,
    ) -> RevokePersonalTokenHandler:
        return RevokePersonalTokenHandler(tokens)

    @provide(scope=Scope.ACTION)
    def create_personal_token_handler(
        self,
        tokens: ApiTokenRepository,
        hasher: Annotated[TokenHasher, FromComponent("")],
        generator: Annotated[TokenGenerator, FromComponent("")],
        scope_policy: Annotated[IdentityTokenScopePolicy, FromComponent("")],
    ) -> CreatePersonalTokenHandler:
        return CreatePersonalTokenHandler(
            tokens,
            hasher,
            generator,
            scope_policy.scopes,
        )

    @provide(scope=Scope.ACTION)
    def rotate_personal_token_handler(
        self,
        tokens: ApiTokenRepository,
        hasher: Annotated[TokenHasher, FromComponent("")],
        generator: Annotated[TokenGenerator, FromComponent("")],
        scope_policy: Annotated[IdentityTokenScopePolicy, FromComponent("")],
    ) -> RotatePersonalTokenHandler:
        return RotatePersonalTokenHandler(
            tokens,
            hasher,
            generator,
            scope_policy.scopes,
        )

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
        hasher: Annotated[TokenHasher, FromComponent("")],
        settings: Annotated[Settings, FromComponent("")],
    ) -> LogoutHandler:
        return LogoutHandler(repository, hasher, settings.browser_allowed_origins)

    @provide(scope=Scope.ACTION)
    def revoke_all_sessions_handler(
        self,
        repository: SessionRepository,
        hasher: Annotated[TokenHasher, FromComponent("")],
        settings: Annotated[Settings, FromComponent("")],
    ) -> RevokeAllSessionsHandler:
        return RevokeAllSessionsHandler(repository, hasher, settings.browser_allowed_origins)

    @provide(scope=Scope.ACTION)
    def revoke_session_handler(
        self,
        repository: SessionRepository,
        hasher: Annotated[TokenHasher, FromComponent("")],
        settings: Annotated[Settings, FromComponent("")],
    ) -> RevokeSessionHandler:
        return RevokeSessionHandler(repository, hasher, settings.browser_allowed_origins)

    @provide(scope=Scope.ACTION)
    def authenticate_session_handler(
        self,
        repository: SessionRepository,
        hasher: Annotated[TokenHasher, FromComponent("")],
    ) -> AuthenticateSessionHandler:
        return AuthenticateSessionHandler(repository, hasher)

    @provide(scope=Scope.ACTION)
    def list_sessions_handler(
        self,
        repository: SessionRepository,
        hasher: Annotated[TokenHasher, FromComponent("")],
    ) -> ListSessionsHandler:
        return ListSessionsHandler(repository, hasher)

    @provide(scope=Scope.ACTION)
    def update_profile_handler(
        self,
        users: UserRepository,
    ) -> UpdateProfileHandler:
        return UpdateProfileHandler(users)

    @provide(scope=Scope.ACTION)
    def read_profile_handler(
        self,
        users: UserRepository,
        repository: SessionRepository,
        hasher: Annotated[TokenHasher, FromComponent("")],
    ) -> ReadProfileHandler:
        return ReadProfileHandler(users, repository, hasher)

    @provide(scope=Scope.ACTION)
    def security_history_handler(
        self,
        users: UserRepository,
        repository: SessionRepository,
        hasher: Annotated[TokenHasher, FromComponent("")],
    ) -> SecurityHistoryHandler:
        return SecurityHistoryHandler(users, repository, hasher)

    @provide(scope=Scope.ACTION)
    def rotate_csrf_handler(
        self,
        repository: SessionRepository,
        hasher: Annotated[TokenHasher, FromComponent("")],
        generator: Annotated[TokenGenerator, FromComponent("")],
    ) -> RotateCsrfHandler:
        return RotateCsrfHandler(repository, hasher, generator)

    @provide(scope=Scope.ACTION)
    def select_active_project_handler(
        self,
        repository: SessionRepository,
        hasher: Annotated[TokenHasher, FromComponent("")],
        generator: Annotated[TokenGenerator, FromComponent("")],
        settings: Annotated[Settings, FromComponent("")],
    ) -> SelectActiveProjectHandler:
        return SelectActiveProjectHandler(
            repository, hasher, generator, settings.browser_allowed_origins
        )

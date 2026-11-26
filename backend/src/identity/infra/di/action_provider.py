"""Per-dispatch Identity bindings isolated to Dishka's ACTION component."""

from typing import Annotated

from dishka import FromComponent, Provider, Scope, alias, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.application.api_tokens.manage_personal_tokens import (
    CreatePersonalTokenHandler,
    RotatePersonalTokenHandler,
)
from identity.application.interfaces.security import TokenGenerator, TokenHasher
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.domain.interfaces.project_access import IdentityProjectAccess
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository
from identity.infra.di.providers import IdentityTokenScopePolicy
from identity.infra.module import IDENTITY_HANDLER_REGISTRY, IDENTITY_REQUEST_MESSAGES
from identity.infra.persistence.repositories.sessions import SQLAlchemySessionRepository
from identity.infra.persistence.repositories.users import SQLAlchemyUserRepository
from shared.infra.dispatch import register_handlers
from shared.infra.persistence.unit_of_work import SqlAlchemyUnitOfWork


class IdentityActionProvider(Provider):
    """Create one session and all session-bound Identity adapters per dispatch."""

    def __init__(self, *, component: str) -> None:
        super().__init__(component=component)
        register_handlers(
            self,
            IDENTITY_HANDLER_REGISTRY,
            scope=Scope.ACTION,
            exclude_messages=IDENTITY_REQUEST_MESSAGES,
            factories={
                CreatePersonalTokenHandler: self.create_personal_token_handler,
                RotatePersonalTokenHandler: self.rotate_personal_token_handler,
            },
        )

    hasher = alias(TokenHasher, component="")
    generator = alias(TokenGenerator, component="")

    @provide(scope=Scope.ACTION)
    def session(
        self,
        sessions: Annotated[async_sessionmaker[AsyncSession], FromComponent("")],
    ) -> AsyncSession:
        return sessions()

    unit_of_work = provide(SqlAlchemyUnitOfWork, scope=Scope.ACTION)

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

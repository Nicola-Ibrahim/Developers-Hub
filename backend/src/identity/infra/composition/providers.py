"""Declarative bindings; this is the only layer selecting concrete implementations."""

from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from dishka import AsyncContainer, Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.accounts.change_password.handler import ChangePasswordHandler
from identity.application.accounts.complete_password_setup.handler import (
    CompletePasswordSetupHandler,
)
from identity.application.accounts.create_user.handler import CreateUserHandler
from identity.application.accounts.set_user_status.handler import SetUserStatusHandler
from identity.application.accounts.start_password_setup.handler import StartPasswordSetupHandler
from identity.application.api_tokens.authenticate_api_token.handler import (
    AuthenticateApiTokenHandler,
)
from identity.application.api_tokens.issue_api_token.handler import IssueApiTokenHandler
from identity.application.api_tokens.revoke_api_token.handler import RevokeApiTokenHandler
from identity.application.authentication.authenticate_session.handler import (
    AuthenticateSessionHandler,
)
from identity.application.authentication.login.handler import LoginHandler
from identity.application.authentication.logout.handler import LogoutHandler
from identity.application.interfaces.authorization import AuthorizationDecisionPort
from identity.application.interfaces.browser_tokens import BrowserSessionTokenVerifier
from identity.application.interfaces.browser_transactions import BrowserTransaction
from identity.application.interfaces.dispatch import IdentityModule
from identity.application.interfaces.security import PasswordHasher, TokenGenerator, TokenHasher
from identity.application.interfaces.token_operations import ApiTokenTransaction
from identity.application.sessions.list_sessions.handler import ListSessionsHandler
from identity.application.sessions.revoke_all_sessions.handler import RevokeAllSessionsHandler
from identity.application.sessions.revoke_session.handler import RevokeSessionHandler
from identity.application.sessions.rotate_csrf.handler import RotateCsrfHandler
from identity.application.sessions.select_active_project.handler import (
    SelectActiveProjectHandler,
)
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.infra.authorization.opa import OpaAuthorizationClient
from identity.infra.composition.api_token_transactions import (
    IssueApiTokenToFile,
    SqlAlchemyApiTokenTransaction,
)
from identity.infra.composition.module import IdentityModuleDispatcher
from identity.infra.composition.session_revocation_unit_of_work import (
    IdentitySessionRevocationUnitOfWork,
)
from identity.infra.persistence.repositories.accounts_sessions import SQLAlchemyIdentityRepository
from identity.infra.persistence.repositories.api_tokens import SQLAlchemyApiTokenRepository
from identity.infra.persistence.repositories.session_revocation import (
    SQLAlchemySessionRevocationRepository,
)
from identity.infra.security.browser_tokens import JwtBrowserSessionTokens
from identity.infra.security.login_verifier import LoginCredentialVerifier
from identity.infra.security.passwords import ScryptPasswordHasher
from identity.infra.security.tokens import PepperedTokenHasher, SecureTokenGenerator
from shared.infra.clock import Clock
from shared.infra.persistence.unit_of_work import SqlAlchemyUnitOfWork
from shared.infra.settings import Settings


@dataclass(frozen=True, slots=True)
class IdentityTokenScopePolicy:
    scopes: tuple[str, ...]


class IdentityProvider(Provider):
    password_hasher = provide(ScryptPasswordHasher, provides=PasswordHasher, scope=Scope.APP)

    @provide(scope=Scope.APP)
    def browser_session_tokens(self, settings: Settings) -> JwtBrowserSessionTokens:
        return JwtBrowserSessionTokens(settings.token_pepper.get_secret_value())

    @provide(scope=Scope.APP)
    def browser_session_token_verifier(
        self, tokens: JwtBrowserSessionTokens
    ) -> BrowserSessionTokenVerifier:
        return tokens

    @provide(scope=Scope.REQUEST)
    def create_user(
        self, transaction: BrowserTransaction, passwords: PasswordHasher, clock: Clock
    ) -> CreateUserHandler:
        return CreateUserHandler(transaction, passwords, clock)

    @provide(scope=Scope.REQUEST)
    def set_user_status(
        self, transaction: BrowserTransaction, clock: Clock
    ) -> SetUserStatusHandler:
        return SetUserStatusHandler(transaction, clock)

    @provide(scope=Scope.REQUEST)
    def start_password_setup(
        self,
        transaction: BrowserTransaction,
        clock: Clock,
        generator: TokenGenerator,
        hasher: TokenHasher,
    ) -> StartPasswordSetupHandler:
        return StartPasswordSetupHandler(transaction, clock, generator.generate, hasher.digest)

    @provide(scope=Scope.REQUEST)
    def complete_password_setup(
        self,
        transaction: BrowserTransaction,
        clock: Clock,
        hasher: TokenHasher,
        passwords: PasswordHasher,
    ) -> CompletePasswordSetupHandler:
        return CompletePasswordSetupHandler(transaction, passwords, clock, hasher.digest)

    @provide(scope=Scope.REQUEST)
    def identity_module(self, container: AsyncContainer) -> IdentityModule:
        return IdentityModuleDispatcher(container)

    @provide(scope=Scope.APP)
    async def opa_http_client(self) -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient(trust_env=False) as client:
            yield client

    @provide(scope=Scope.REQUEST, provides=AuthorizationDecisionPort)
    def authorization_decisions(
        self, client: httpx.AsyncClient, settings: Settings
    ) -> OpaAuthorizationClient:
        return OpaAuthorizationClient(settings.opa_url, client)

    token_transaction = provide(
        SqlAlchemyApiTokenTransaction,
        provides=ApiTokenTransaction,
        scope=Scope.REQUEST,
    )

    @provide(scope=Scope.REQUEST)
    def authenticate_browser_session(
        self, transaction: BrowserTransaction, clock: Clock, hasher: TokenHasher
    ) -> AuthenticateSessionHandler:
        return AuthenticateSessionHandler(transaction, clock, hasher.digest)

    @provide(scope=Scope.REQUEST)
    def rotate_browser_csrf(
        self,
        transaction: BrowserTransaction,
        clock: Clock,
        hasher: TokenHasher,
        generator: TokenGenerator,
    ) -> RotateCsrfHandler:
        return RotateCsrfHandler(transaction, clock, hasher.digest, generator.generate)

    @provide(scope=Scope.REQUEST)
    def select_browser_project(
        self,
        transaction: BrowserTransaction,
        clock: Clock,
        hasher: TokenHasher,
        generator: TokenGenerator,
        settings: Settings,
    ) -> SelectActiveProjectHandler:
        return SelectActiveProjectHandler(
            transaction, clock, hasher.digest, generator.generate, settings.browser_allowed_origins
        )

    @provide(scope=Scope.REQUEST)
    def logout_browser_session(
        self,
        session: AsyncSession,
        unit: SqlAlchemyUnitOfWork,
        clock: Clock,
        hasher: TokenHasher,
        settings: Settings,
    ) -> LogoutHandler:
        repository = SQLAlchemyIdentityRepository(session)
        return LogoutHandler(
            repository,
            repository,
            IdentitySessionRevocationUnitOfWork(unit),
            clock,
            hasher.digest,
            settings.browser_allowed_origins,
        )

    @provide(scope=Scope.REQUEST)
    def logout_all_browser_sessions(
        self,
        session: AsyncSession,
        unit: SqlAlchemyUnitOfWork,
        clock: Clock,
        hasher: TokenHasher,
        settings: Settings,
    ) -> RevokeAllSessionsHandler:
        repository = SQLAlchemyIdentityRepository(session)
        return RevokeAllSessionsHandler(
            repository,
            repository,
            IdentitySessionRevocationUnitOfWork(unit),
            clock,
            hasher.digest,
            settings.browser_allowed_origins,
        )

    @provide(scope=Scope.REQUEST)
    def list_browser_sessions(
        self, transaction: BrowserTransaction, clock: Clock, hasher: TokenHasher
    ) -> ListSessionsHandler:
        return ListSessionsHandler(transaction, clock, hasher.digest)

    @provide(scope=Scope.REQUEST)
    def revoke_browser_session(
        self,
        session: AsyncSession,
        unit: SqlAlchemyUnitOfWork,
        clock: Clock,
        hasher: TokenHasher,
        settings: Settings,
    ) -> RevokeSessionHandler:
        return RevokeSessionHandler(
            SQLAlchemyIdentityRepository(session),
            SQLAlchemySessionRevocationRepository(session),
            IdentitySessionRevocationUnitOfWork(unit),
            clock,
            hasher.digest,
            settings.browser_allowed_origins,
        )

    @provide(scope=Scope.REQUEST)
    def change_browser_password(
        self,
        transaction: BrowserTransaction,
        clock: Clock,
        hasher: TokenHasher,
        settings: Settings,
        passwords: PasswordHasher,
    ) -> ChangePasswordHandler:
        return ChangePasswordHandler(
            transaction,
            passwords,
            clock,
            hasher.digest,
            settings.browser_allowed_origins,
        )

    @provide(scope=Scope.APP)
    def login_credential_verifier(self, passwords: PasswordHasher) -> LoginCredentialVerifier:
        return LoginCredentialVerifier(passwords)

    @provide(scope=Scope.REQUEST)
    def login_handler(
        self,
        transaction: BrowserTransaction,
        login_credential_verifier: LoginCredentialVerifier,
        generator: TokenGenerator,
        token_hasher: TokenHasher,
        session_token_issuer: JwtBrowserSessionTokens,
        clock: Clock,
        settings: Settings,
    ) -> LoginHandler:
        return LoginHandler(
            transaction,
            login_credential_verifier,
            generator,
            clock,
            token_hasher.digest,
            settings.browser_allowed_origins,
            session_token_issuer,
        )

    @provide(scope=Scope.APP)
    def hasher(self, settings: Settings) -> TokenHasher:
        return PepperedTokenHasher(settings.token_pepper.get_secret_value())

    @provide(scope=Scope.APP)
    def generator(self) -> TokenGenerator:
        return SecureTokenGenerator()

    repository = provide(
        SQLAlchemyApiTokenRepository, provides=ApiTokenRepository, scope=Scope.REQUEST
    )
    authenticate = provide(AuthenticateApiTokenHandler, scope=Scope.REQUEST)
    revoke = provide(RevokeApiTokenHandler, scope=Scope.REQUEST)
    issue_command = provide(IssueApiTokenToFile, scope=Scope.REQUEST)

    @provide(scope=Scope.REQUEST)
    def issue(
        self,
        repository: ApiTokenRepository,
        hasher: TokenHasher,
        generator: TokenGenerator,
        clock: Clock,
        scope_policy: IdentityTokenScopePolicy,
    ) -> IssueApiTokenHandler:
        return IssueApiTokenHandler(
            repository, hasher, generator, clock, scope_policy.scopes, scope_policy.scopes
        )

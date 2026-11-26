"""Declarative bindings; this is the only layer selecting concrete implementations."""

from dataclasses import dataclass

from dishka import AsyncContainer, Provider, Scope, provide

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
from identity.application.api_tokens.revoke_api_token.handler import RevokeApiTokenHandler
from identity.application.authentication.login.handler import LoginHandler
from identity.application.interfaces.dispatch import IdentityModule
from identity.application.interfaces.identity_transactions import IdentityTransaction
from identity.application.interfaces.security import PasswordHasher, TokenGenerator, TokenHasher
from identity.application.interfaces.session_tokens import SessionTokenVerifier
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.infra.composition.module import IdentityModuleDispatcher
from identity.infra.persistence.repositories.api_tokens import SQLAlchemyApiTokenRepository
from identity.infra.security.jwt import JwtSessionTokens
from identity.infra.security.opaque_secrets import PepperedTokenHasher, SecureTokenGenerator
from identity.infra.security.passwords import Argon2idPasswordHasher
from shared.infra.settings import Settings


@dataclass(frozen=True, slots=True)
class IdentityTokenScopePolicy:
    scopes: tuple[str, ...]


class IdentityProvider(Provider):
    password_hasher = provide(Argon2idPasswordHasher, provides=PasswordHasher, scope=Scope.APP)

    @provide(scope=Scope.APP)
    def session_tokens(self, settings: Settings) -> JwtSessionTokens:
        return JwtSessionTokens(settings.token_pepper.get_secret_value())

    @provide(scope=Scope.APP)
    def session_token_verifier(self, tokens: JwtSessionTokens) -> SessionTokenVerifier:
        return tokens

    @provide(scope=Scope.REQUEST)
    def create_user(
        self, transaction: IdentityTransaction, passwords: PasswordHasher
    ) -> CreateUserHandler:
        return CreateUserHandler(transaction, passwords)

    @provide(scope=Scope.REQUEST)
    def set_user_status(self, transaction: IdentityTransaction) -> SetUserStatusHandler:
        return SetUserStatusHandler(transaction)

    @provide(scope=Scope.REQUEST)
    def start_password_setup(
        self,
        transaction: IdentityTransaction,
        generator: TokenGenerator,
        hasher: TokenHasher,
    ) -> StartPasswordSetupHandler:
        return StartPasswordSetupHandler(transaction, generator, hasher)

    @provide(scope=Scope.REQUEST)
    def complete_password_setup(
        self,
        transaction: IdentityTransaction,
        hasher: TokenHasher,
        passwords: PasswordHasher,
    ) -> CompletePasswordSetupHandler:
        return CompletePasswordSetupHandler(transaction, passwords, hasher)

    @provide(scope=Scope.REQUEST)
    def identity_module(self, container: AsyncContainer) -> IdentityModule:
        return IdentityModuleDispatcher(container)

    @provide(scope=Scope.REQUEST)
    def change_password(
        self,
        transaction: IdentityTransaction,
        passwords: PasswordHasher,
    ) -> ChangePasswordHandler:
        return ChangePasswordHandler(transaction, passwords)

    @provide(scope=Scope.REQUEST)
    def login_handler(
        self,
        transaction: IdentityTransaction,
        passwords: PasswordHasher,
        generator: TokenGenerator,
        token_hasher: TokenHasher,
        session_token_issuer: JwtSessionTokens,
    ) -> LoginHandler:
        return LoginHandler(
            transaction,
            passwords,
            generator,
            token_hasher,
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

"""Declarative bindings; this is the only layer selecting concrete implementations."""

from dataclasses import dataclass

from dishka import AsyncContainer, Provider, Scope, alias, provide

from identity.application.accounts.complete_password_setup.handler import (
    CompletePasswordSetupHandler,
)
from identity.application.accounts.create_user.handler import CreateUserHandler
from identity.application.accounts.set_user_status.handler import SetUserStatusHandler
from identity.application.accounts.start_password_setup.handler import StartPasswordSetupHandler
from identity.application.api_tokens.revoke_api_token.handler import RevokeApiTokenHandler
from identity.application.interfaces.dispatch import IdentityModule
from identity.application.interfaces.identity_transactions import IdentityTransaction
from identity.application.interfaces.security import PasswordHasher, TokenGenerator, TokenHasher
from identity.application.interfaces.session_tokens import SessionTokenIssuer, SessionTokenVerifier
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.infra.composition.module import IDENTITY_HANDLER_REGISTRY, IDENTITY_REQUEST_MESSAGES
from identity.infra.composition.module import IdentityModule as RequestIdentityModule
from identity.infra.persistence.repositories.api_tokens import SQLAlchemyApiTokenRepository
from identity.infra.security.jwt import JwtSessionTokens
from identity.infra.security.opaque_secrets import PepperedTokenHasher, SecureTokenGenerator
from identity.infra.security.passwords import Argon2idPasswordHasher
from shared.authorization.credentials import RequestCredentials
from shared.infra.dispatch import register_handlers
from shared.infra.settings import Settings


@dataclass(frozen=True, slots=True)
class IdentityTokenScopePolicy:
    scopes: tuple[str, ...]


class IdentityProvider(Provider):
    def __init__(self) -> None:
        super().__init__()
        register_handlers(
            self,
            IDENTITY_HANDLER_REGISTRY,
            scope=Scope.REQUEST,
            messages=IDENTITY_REQUEST_MESSAGES,
        )

    session_token_issuer = alias(JwtSessionTokens, provides=SessionTokenIssuer)
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

    @provide(scope=Scope.REQUEST, provides=IdentityModule)
    def identity_module(
        self, container: AsyncContainer, credentials: RequestCredentials
    ) -> RequestIdentityModule:
        return RequestIdentityModule(container, credentials)

    @provide(scope=Scope.APP)
    def hasher(self, settings: Settings) -> TokenHasher:
        return PepperedTokenHasher(settings.token_pepper.get_secret_value())

    @provide(scope=Scope.APP)
    def generator(self) -> TokenGenerator:
        return SecureTokenGenerator()

    repository = provide(
        SQLAlchemyApiTokenRepository, provides=ApiTokenRepository, scope=Scope.REQUEST
    )
    revoke = provide(RevokeApiTokenHandler, scope=Scope.REQUEST)

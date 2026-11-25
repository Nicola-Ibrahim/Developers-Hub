"""Personal token operations within Identity's ACTION transaction."""

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

from identity.application.api_tokens.personal_token_messages import (
    CreatePersonalTokenCommand,
    ListPersonalTokensQuery,
    RevokePersonalTokenCommand,
    RotatePersonalTokenCommand,
)
from identity.application.interfaces.security import TokenGenerator, TokenHasher
from identity.application.shared.session_security import (
    BrowserMutationAuthorizer,
    require_browser_origin,
)
from identity.domain.browser_errors import BrowserAuthenticationRejected
from identity.domain.errors import IdentityValidationError
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.records import ApiTokenAuditEvent, PersonalApiToken, SessionPrincipal
from identity.domain.value_objects.token_scopes import TokenScopes


class PersonalTokenHandler:
    def __init__(
        self,
        tokens: ApiTokenRepository,
        sessions: SessionRepository,
        hasher: TokenHasher,
        generator: TokenGenerator,
        clock: Callable[[], datetime],
        allowed_scopes: tuple[str, ...],
        allowed_origins: tuple[str, ...],
    ) -> None:
        self.tokens, self.sessions = tokens, sessions
        self.hasher, self.generator, self.clock = hasher, generator, clock
        self.allowed_scopes, self.allowed_origins = allowed_scopes, allowed_origins

    async def execute(
        self,
        command: ListPersonalTokensQuery
        | CreatePersonalTokenCommand
        | RotatePersonalTokenCommand
        | RevokePersonalTokenCommand,
    ) -> tuple[PersonalApiToken, ...] | tuple[PersonalApiToken, str] | bool | None:
        if isinstance(command, ListPersonalTokensQuery):
            principal = await self._authenticate(command.session_token, command.project_id)
            return await self.tokens.list_personal_tokens(principal.user_id, command.project_id)

        require_browser_origin(command.origin, self.allowed_origins)
        locked_token = None
        if isinstance(command, (RotatePersonalTokenCommand, RevokePersonalTokenCommand)):
            locked_token = await self.tokens.lock_personal_token(command.token_id)
        principal = await BrowserMutationAuthorizer(
            self.sessions, self.clock, self.hasher.digest, self.allowed_origins
        ).authorize_mutation(command.session_token, command.csrf_token, command.origin)
        if isinstance(command, CreatePersonalTokenCommand):
            return await self._create(principal, command)
        if isinstance(command, RotatePersonalTokenCommand):
            if locked_token is None or locked_token.user_id != principal.user_id:
                return None
            return await self._rotate(principal, command.token_id)
        if locked_token is None or locked_token.user_id != principal.user_id:
            return False
        return await self._revoke(principal, command.token_id)

    async def _authenticate(self, token: str, project_id: UUID | None) -> SessionPrincipal:
        result = await self.sessions.authenticate_session(
            token_digest=self.hasher.digest(token), project_id=project_id, now=self.clock()
        )
        if result is None:
            raise BrowserAuthenticationRejected()
        return result[0]

    async def _create(
        self, principal: SessionPrincipal, command: CreatePersonalTokenCommand
    ) -> tuple[PersonalApiToken, str]:
        if principal.project_id is None:
            raise IdentityValidationError("Select a project before creating a token")
        if not command.name.strip() or len(command.name) > 100 or not 1 <= command.hours <= 720:
            raise IdentityValidationError("Invalid token name or duration")
        scopes = TokenScopes.select(
            command.scopes, allowed=self.allowed_scopes, defaults=self.allowed_scopes
        ).values
        now, secret = self.clock(), self.generator.generate()
        token_id = await self.tokens.create_personal_token(
            user_id=principal.user_id,
            project_id=principal.project_id,
            name=command.name.strip(),
            digest=self.hasher.digest(secret),
            scopes=scopes,
            created_at=now,
            expires_at=now + timedelta(hours=command.hours),
        )
        await self.tokens.record_token_audit(
            ApiTokenAuditEvent(
                principal.user_id, principal.project_id, "token_issued", "succeeded", token_id
            )
        )
        return PersonalApiToken(
            token_id,
            command.name.strip(),
            principal.project_id,
            scopes,
            now + timedelta(hours=command.hours),
            None,
        ), secret

    async def _rotate(
        self, principal: SessionPrincipal, token_id: UUID
    ) -> tuple[PersonalApiToken, str] | None:
        now, secret = self.clock(), self.generator.generate()
        token = await self.tokens.rotate_personal_token(
            user_id=principal.user_id,
            token_id=token_id,
            digest=self.hasher.digest(secret),
            now=now,
            allowed_scopes=self.allowed_scopes,
        )
        if token is None:
            return None
        await self.tokens.record_token_audit(
            ApiTokenAuditEvent(
                principal.user_id, token.project_id, "token_rotated", "succeeded", token.token_id
            )
        )
        return token, secret

    async def _revoke(self, principal: SessionPrincipal, token_id: UUID) -> bool:
        return await self.tokens.revoke_personal_token(
            user_id=principal.user_id, token_id=token_id, now=self.clock()
        )

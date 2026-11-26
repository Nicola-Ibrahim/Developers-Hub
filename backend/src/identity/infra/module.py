"""Explicit Identity message registration and application dispatch."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TypeVar, cast
from uuid import UUID

from dishka import AsyncContainer, Scope

from identity.application.accounts.change_password.command import ChangePasswordCommand
from identity.application.accounts.change_password.handler import ChangePasswordHandler
from identity.application.api_tokens.authenticate_api_token.handler import (
    AuthenticateApiTokenHandler,
)
from identity.application.api_tokens.authenticate_api_token.query import AuthenticateApiTokenQuery
from identity.application.api_tokens.manage_personal_tokens import (
    CreatePersonalTokenHandler,
    PersonalTokenQueryHandler,
    RevokePersonalTokenHandler,
    RotatePersonalTokenHandler,
)
from identity.application.api_tokens.personal_token_messages import (
    CreatePersonalTokenCommand,
    ListPersonalTokensQuery,
    RevokePersonalTokenCommand,
    RotatePersonalTokenCommand,
)
from identity.application.authentication.authenticate_session.handler import (
    AuthenticateSessionHandler,
)
from identity.application.authentication.authenticate_session.query import (
    AuthenticateSessionQuery,
)
from identity.application.authentication.login.command import LoginCommand
from identity.application.authentication.login.handler import LoginHandler
from identity.application.authentication.logout.command import LogoutCommand
from identity.application.authentication.logout.handler import LogoutHandler
from identity.application.interfaces.dispatch import ActionPrecondition
from identity.application.interfaces.dispatch import IdentityModule as IdentityModuleContract
from identity.application.interfaces.security import TokenHasher
from identity.application.profile.handlers import (
    ReadProfileHandler,
    SecurityHistoryHandler,
    UpdateProfileHandler,
)
from identity.application.profile.profile_query import ProfileQuery, SecurityHistoryQuery
from identity.application.profile.update_profile import UpdateProfileCommand
from identity.application.sessions.list_sessions.handler import ListSessionsHandler
from identity.application.sessions.list_sessions.query import ListSessionsQuery
from identity.application.sessions.revoke_all_sessions.command import RevokeAllSessionsCommand
from identity.application.sessions.revoke_all_sessions.handler import RevokeAllSessionsHandler
from identity.application.sessions.revoke_session.command import RevokeSessionCommand
from identity.application.sessions.revoke_session.handler import RevokeSessionHandler
from identity.application.sessions.rotate_csrf.command import RotateCsrfCommand
from identity.application.sessions.rotate_csrf.handler import RotateCsrfHandler
from identity.application.sessions.select_active_project.command import (
    SelectActiveProjectCommand,
)
from identity.application.sessions.select_active_project.handler import (
    SelectActiveProjectHandler,
)
from identity.application.shared.errors import IdentityUnavailable
from identity.domain.errors import AuthenticationRejected
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.records import SessionPrincipal
from identity.domain.session_errors import SessionAuthenticationRejected
from shared.authorization.credentials import RequestCredentials, SessionCredentials
from shared.authorization.dispatch import require_authorized
from shared.authorization.interfaces import AuthorizationDecisionPort, AuthorizationDenied
from shared.authorization.models import AuthorizationRequest
from shared.dispatch import Command, HandlerRegistry, Mediator, Query
from shared.infra.persistence.unit_of_work import DatabaseUnavailable, SqlAlchemyUnitOfWork

ResultT = TypeVar("ResultT")

IDENTITY_HANDLER_REGISTRY = HandlerRegistry(
    commands=(
        (LoginCommand, LoginHandler),
        (RotateCsrfCommand, RotateCsrfHandler),
        (SelectActiveProjectCommand, SelectActiveProjectHandler),
        (LogoutCommand, LogoutHandler),
        (RevokeAllSessionsCommand, RevokeAllSessionsHandler),
        (RevokeSessionCommand, RevokeSessionHandler),
        (ChangePasswordCommand, ChangePasswordHandler),
        (UpdateProfileCommand, UpdateProfileHandler),
        (CreatePersonalTokenCommand, CreatePersonalTokenHandler),
        (RotatePersonalTokenCommand, RotatePersonalTokenHandler),
        (RevokePersonalTokenCommand, RevokePersonalTokenHandler),
    ),
    queries=(
        (AuthenticateApiTokenQuery, AuthenticateApiTokenHandler),
        (AuthenticateSessionQuery, AuthenticateSessionHandler),
        (ListSessionsQuery, ListSessionsHandler),
        (ProfileQuery, ReadProfileHandler),
        (SecurityHistoryQuery, SecurityHistoryHandler),
        (ListPersonalTokensQuery, PersonalTokenQueryHandler),
    ),
)


IDENTITY_REQUEST_MESSAGES = (LoginCommand, ChangePasswordCommand, AuthenticateApiTokenQuery)


class IdentityModule(IdentityModuleContract):
    """Route public Identity messages and secure browser operations internally."""

    def __init__(self, container: AsyncContainer, credentials: RequestCredentials) -> None:
        self._container = container
        self._credentials = credentials
        self._mediator = Mediator(IDENTITY_HANDLER_REGISTRY, container.get)

    async def execute(self, command: Command[ResultT]) -> ResultT:
        if type(command) not in IDENTITY_HANDLER_REGISTRY.commands:
            return await self._mediator.execute(command)
        if isinstance(command, LoginCommand):
            return cast(ResultT, await self._mediator.execute(command))
        precondition = await self._precondition(command)
        if isinstance(command, ChangePasswordCommand):
            handler = cast(ChangePasswordHandler, await self._mediator.resolve(command))
            await handler.execute(command, precondition)
            return cast(ResultT, None)
        return await self._dispatch_action(lambda mediator: mediator.execute(command), precondition)

    async def query(self, query: Query[ResultT]) -> ResultT:
        if type(query) not in IDENTITY_HANDLER_REGISTRY.queries:
            return await self._mediator.query(query)
        if isinstance(query, AuthenticateApiTokenQuery):
            if query.token is not None and query.token != self._credentials.identity:
                raise AuthenticationRejected()
            return cast(ResultT, await self._mediator.query(query))
        if isinstance(query, AuthenticateSessionQuery):
            identity = self._session_credentials()
            if query.session_token != identity.session_token or (
                query.csrf_token is not None and query.csrf_token != identity.csrf_token
            ):
                raise SessionAuthenticationRejected()
            return cast(
                ResultT, await self._dispatch_action(lambda mediator: mediator.query(query))
            )
        return await self._dispatch_action(
            lambda mediator: mediator.query(query), await self._precondition(query)
        )

    async def _precondition(self, message: object) -> ActionPrecondition:
        credentials = self._session_credentials()
        token = credentials.session_token
        if token is None:
            raise SessionAuthenticationRejected()
        if getattr(message, "session_token", token) != token:
            raise SessionAuthenticationRejected()
        hasher = await self._container.get(TokenHasher)
        digest = hasher.digest(token)
        verify_csrf = isinstance(message, Command) and not isinstance(message, RotateCsrfCommand)
        csrf_digest = (
            hasher.digest(credentials.csrf_token)
            if verify_csrf and credentials.csrf_token
            else None
        )

        async def check(
            sessions: SessionRepository, tokens: ApiTokenRepository | None
        ) -> SessionPrincipal:
            token_id = None
            target = None
            if isinstance(message, (RotatePersonalTokenCommand, RevokePersonalTokenCommand)):
                token_id = message.token_id
                if tokens is None:
                    raise SessionAuthenticationRejected()
                # The token row must be acquired before session authentication locks the user.
                target = await tokens.lock_personal_token(token_id, user_id=message.actor_id)
            principal = await sessions.authorize_session_operation(
                digest,
                credentials.project_id,
                datetime.now(UTC),
                lock_for_mutation=verify_csrf,
            )
            if principal is None or (
                verify_csrf
                and (csrf_digest is None or not await sessions.validate_csrf(digest, csrf_digest))
            ):
                raise SessionAuthenticationRejected()
            if getattr(message, "actor_id", principal.user_id) != principal.user_id:
                raise SessionAuthenticationRejected()

            kind = "session"
            owner_id: UUID | None = principal.user_id
            resource_id = token_id
            project_id = principal.project_id
            role = principal.role
            denied = AuthorizationDenied()
            if isinstance(message, (ProfileQuery, SecurityHistoryQuery, UpdateProfileCommand)):
                kind = "profile"
            if isinstance(
                message,
                (
                    CreatePersonalTokenCommand,
                    ListPersonalTokensQuery,
                    RotatePersonalTokenCommand,
                    RevokePersonalTokenCommand,
                ),
            ):
                kind = "token"
            if token_id is not None:
                owner_id = target.user_id if target is not None else None
                if owner_id != principal.user_id:
                    denied = AuthorizationDenied(404, "not_found", "Token not found")
            if isinstance(message, CreatePersonalTokenCommand) and message.project_id != project_id:
                raise SessionAuthenticationRejected()
            if isinstance(message, RevokeSessionCommand):
                resource_id = message.session_id
            if isinstance(message, SelectActiveProjectCommand):
                project_id = message.project_id
                membership = next(
                    (item for item in principal.memberships if item.project_id == project_id), None
                )
                if membership is None:
                    raise SessionAuthenticationRejected()
                role = membership.role

            authorizer = await self._container.get(AuthorizationDecisionPort)
            await require_authorized(
                authorizer,
                message,
                AuthorizationRequest(
                    principal.user_id,
                    "",
                    kind,
                    resource_id,
                    project_id,
                    project_id,
                    role,
                    tuple(principal.scopes),
                    owner_id,
                ),
                denied,
            )
            return principal

        return check

    def _session_credentials(self) -> SessionCredentials:
        identity = self._credentials.identity
        if not isinstance(identity, SessionCredentials):
            raise SessionAuthenticationRejected()
        return identity

    async def _dispatch_action(
        self,
        dispatch: Callable[[Mediator], Awaitable[ResultT]],
        precondition: ActionPrecondition | None = None,
    ) -> ResultT:
        async with self._container(scope=Scope.ACTION) as action_container:
            mediator = Mediator(
                IDENTITY_HANDLER_REGISTRY,
                lambda handler_type: action_container.get(
                    handler_type, component="identity_action"
                ),
            )
            unit = await action_container.get(SqlAlchemyUnitOfWork, component="identity_action")

            async def run() -> ResultT:
                if precondition is not None:
                    sessions = await action_container.get(
                        SessionRepository, component="identity_action"
                    )
                    tokens = await action_container.get(
                        ApiTokenRepository, component="identity_action"
                    )
                    await precondition(sessions, tokens)
                return await dispatch(mediator)

            try:
                return await unit.run(run, lambda result: result)
            except DatabaseUnavailable as error:
                raise IdentityUnavailable() from error

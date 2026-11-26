"""Explicit identity message registration and lazy module dispatch."""

from collections.abc import Awaitable, Callable
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
from identity.application.authentication.authenticate_session.query import AuthenticateSessionQuery
from identity.application.authentication.login.command import LoginCommand
from identity.application.authentication.login.handler import LoginHandler
from identity.application.authentication.logout.command import LogoutCommand
from identity.application.authentication.logout.handler import LogoutHandler
from identity.application.interfaces.dispatch import ActionPrecondition
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
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.records import SessionPrincipal
from identity.domain.session_errors import SessionAuthenticationRejected
from shared.authorization.dispatch import require_authorized
from shared.authorization.interfaces import AuthorizationDecisionPort, AuthorizationDenied
from shared.authorization.models import AuthorizationRequest
from shared.dispatch import Command, HandlerRegistry, ModuleDispatcher, Query, UnsupportedMessage
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
    required_commands=(
        LoginCommand,
        RotateCsrfCommand,
        SelectActiveProjectCommand,
        LogoutCommand,
        RevokeAllSessionsCommand,
        RevokeSessionCommand,
        ChangePasswordCommand,
        UpdateProfileCommand,
        CreatePersonalTokenCommand,
        RotatePersonalTokenCommand,
        RevokePersonalTokenCommand,
    ),
    required_queries=(
        AuthenticateApiTokenQuery,
        AuthenticateSessionQuery,
        ListSessionsQuery,
        ProfileQuery,
        SecurityHistoryQuery,
        ListPersonalTokensQuery,
    ),
)


class IdentityModuleDispatcher(ModuleDispatcher):
    def __init__(self, container: AsyncContainer) -> None:
        self._container = container
        super().__init__(IDENTITY_HANDLER_REGISTRY, container.get)

    async def execute(self, command: Command[ResultT]) -> ResultT:
        if type(command) not in IDENTITY_HANDLER_REGISTRY.commands:
            return await super().execute(command)
        if isinstance(command, LoginCommand):
            return await super().execute(cast(Command[ResultT], command))
        raise SessionAuthenticationRejected()

    async def execute_with_precondition(
        self, command: Command[ResultT], precondition: ActionPrecondition
    ) -> ResultT:
        if type(command) not in IDENTITY_HANDLER_REGISTRY.commands or isinstance(
            command, LoginCommand
        ):
            raise UnsupportedMessage("Unsupported protected command")
        guard = self._secured_precondition(command, precondition)
        if isinstance(command, ChangePasswordCommand):
            handler = await self._container.get(ChangePasswordHandler)
            await handler.execute(command, guard)
            return cast(ResultT, None)
        return await self._dispatch_action(lambda dispatcher: dispatcher.execute(command), guard)

    async def query(self, query: Query[ResultT]) -> ResultT:
        if type(query) not in IDENTITY_HANDLER_REGISTRY.queries:
            return await super().query(query)
        if type(query) is AuthenticateApiTokenQuery:
            return await super().query(cast(Query[ResultT], query))
        if type(query) is AuthenticateSessionQuery:
            return await self._dispatch_action(
                lambda dispatcher: dispatcher.query(cast(Query[ResultT], query))
            )
        raise SessionAuthenticationRejected()

    async def query_with_precondition(
        self, query: Query[ResultT], precondition: ActionPrecondition
    ) -> ResultT:
        if type(query) not in IDENTITY_HANDLER_REGISTRY.queries or isinstance(
            query, (AuthenticateApiTokenQuery, AuthenticateSessionQuery)
        ):
            raise UnsupportedMessage("Unsupported protected query")
        return await self._dispatch_action(
            lambda dispatcher: dispatcher.query(query),
            self._secured_precondition(query, precondition),
        )

    def _secured_precondition(
        self, message: object, authenticate: ActionPrecondition
    ) -> ActionPrecondition:
        async def check(
            sessions: SessionRepository, tokens: ApiTokenRepository | None
        ) -> SessionPrincipal:
            token_id = None
            target = None
            if isinstance(message, (RotatePersonalTokenCommand, RevokePersonalTokenCommand)):
                token_id = message.token_id
                if tokens is None:
                    raise SessionAuthenticationRejected()
                # Token revocation and authentication acquire the token row first.
                target = await tokens.lock_personal_token(token_id, user_id=message.actor_id)
            principal = await authenticate(sessions, tokens)
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

    async def _dispatch_action(
        self,
        dispatch: Callable[[ModuleDispatcher], Awaitable[ResultT]],
        precondition: ActionPrecondition | None = None,
    ) -> ResultT:
        async with self._container(scope=Scope.ACTION) as action_container:
            dispatcher = ModuleDispatcher(
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
                return await dispatch(dispatcher)

            try:
                return await unit.run(
                    run,
                    lambda result: result,
                )
            except DatabaseUnavailable as error:
                raise IdentityUnavailable() from error

"""Explicit identity message registration and lazy module dispatch."""

from collections.abc import Awaitable, Callable
from typing import TypeVar, cast

from dishka import AsyncContainer, Scope

from identity.application.accounts.change_password.command import ChangePasswordCommand
from identity.application.accounts.change_password.handler import ChangePasswordHandler
from identity.application.api_tokens.authenticate_api_token.handler import (
    AuthenticateApiTokenHandler,
)
from identity.application.api_tokens.authenticate_api_token.query import AuthenticateApiTokenQuery
from identity.application.authentication.authenticate_session.handler import (
    AuthenticateSessionHandler,
)
from identity.application.authentication.authenticate_session.query import AuthenticateSessionQuery
from identity.application.authentication.login.command import LoginCommand
from identity.application.authentication.login.handler import LoginHandler
from identity.application.authentication.logout.command import LogoutCommand
from identity.application.authentication.logout.handler import LogoutHandler
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
from shared.dispatch import Command, HandlerRegistry, ModuleDispatcher, Query
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
    ),
    queries=(
        (AuthenticateApiTokenQuery, AuthenticateApiTokenHandler),
        (AuthenticateSessionQuery, AuthenticateSessionHandler),
        (ListSessionsQuery, ListSessionsHandler),
    ),
    required_commands=(
        LoginCommand,
        RotateCsrfCommand,
        SelectActiveProjectCommand,
        LogoutCommand,
        RevokeAllSessionsCommand,
        RevokeSessionCommand,
        ChangePasswordCommand,
    ),
    required_queries=(
        AuthenticateApiTokenQuery,
        AuthenticateSessionQuery,
        ListSessionsQuery,
    ),
)


class IdentityModuleDispatcher(ModuleDispatcher):
    def __init__(self, container: AsyncContainer) -> None:
        self._container = container
        super().__init__(IDENTITY_HANDLER_REGISTRY, container.get)

    async def execute(self, command: Command[ResultT]) -> ResultT:
        if type(command) not in IDENTITY_HANDLER_REGISTRY.commands:
            return await super().execute(command)
        if type(command) in (LoginCommand, ChangePasswordCommand):
            return await super().execute(command)
        return await self._dispatch_action(lambda dispatcher: dispatcher.execute(command))

    async def query(self, query: Query[ResultT]) -> ResultT:
        if type(query) not in IDENTITY_HANDLER_REGISTRY.queries:
            return await super().query(query)
        if type(query) is AuthenticateApiTokenQuery:
            return await super().query(cast(Query[ResultT], query))
        return await self._dispatch_action(lambda dispatcher: dispatcher.query(query))

    async def _dispatch_action(
        self, dispatch: Callable[[ModuleDispatcher], Awaitable[ResultT]]
    ) -> ResultT:
        async with self._container(scope=Scope.ACTION) as action_container:
            dispatcher = ModuleDispatcher(
                IDENTITY_HANDLER_REGISTRY,
                lambda handler_type: action_container.get(
                    handler_type, component="identity_action"
                ),
            )
            unit = await action_container.get(SqlAlchemyUnitOfWork, component="identity_action")
            try:
                return await unit.run(
                    lambda: dispatch(dispatcher),
                    lambda result: result,
                )
            except DatabaseUnavailable as error:
                raise IdentityUnavailable() from error

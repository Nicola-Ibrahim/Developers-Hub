"""Identity message registration and lazy handler resolution."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from identity.application.accounts.change_password.command import ChangePasswordCommand
from identity.application.api_tokens.authenticate_api_token.handler import (
    AuthenticateApiTokenHandler,
)
from identity.application.api_tokens.authenticate_api_token.query import AuthenticateApiTokenQuery
from identity.application.api_tokens.personal_token_messages import (
    CreatePersonalTokenCommand,
    ListPersonalTokensQuery,
    RevokePersonalTokenCommand,
    RotatePersonalTokenCommand,
)
from identity.application.authentication.authenticate_session.query import AuthenticateSessionQuery
from identity.application.authentication.login.command import LoginCommand
from identity.application.authentication.login.handler import LoginHandler
from identity.application.authentication.logout.command import LogoutCommand
from identity.application.authentication.logout.handler import LogoutHandler
from identity.application.profile.profile_query import ProfileQuery, SecurityHistoryQuery
from identity.application.profile.update_profile import UpdateProfileCommand
from identity.application.sessions.list_sessions.query import ListSessionsQuery
from identity.application.sessions.revoke_all_sessions.command import RevokeAllSessionsCommand
from identity.application.sessions.revoke_all_sessions.handler import RevokeAllSessionsHandler
from identity.application.sessions.revoke_session.command import RevokeSessionCommand
from identity.application.sessions.revoke_session.handler import RevokeSessionHandler
from identity.application.sessions.rotate_csrf.command import RotateCsrfCommand
from identity.application.sessions.select_active_project.command import (
    SelectActiveProjectCommand,
)
from identity.domain.aggregates.api_token import ApiTokenAuthenticationDetails
from identity.infra.composition.api_token_transactions import (
    SqlAlchemyApiTokenTransaction,
)
from identity.infra.composition.module import (
    IDENTITY_HANDLER_REGISTRY,
    IdentityModuleDispatcher,
)
from shared.dispatch import HandlerRegistry, RegistrationError, UnsupportedMessage
from shared.infra.persistence.unit_of_work import SqlAlchemyUnitOfWork


def test_identity_messages_have_explicit_complete_registrations() -> None:
    assert (
        IDENTITY_HANDLER_REGISTRY.queries[AuthenticateApiTokenQuery] is AuthenticateApiTokenHandler
    )
    assert IDENTITY_HANDLER_REGISTRY.commands[LoginCommand] is LoginHandler
    assert IDENTITY_HANDLER_REGISTRY.commands[LogoutCommand] is LogoutHandler
    assert IDENTITY_HANDLER_REGISTRY.commands[RevokeAllSessionsCommand] is RevokeAllSessionsHandler
    assert IDENTITY_HANDLER_REGISTRY.commands[RevokeSessionCommand] is RevokeSessionHandler
    assert set(IDENTITY_HANDLER_REGISTRY.commands) == {
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
    }
    assert set(IDENTITY_HANDLER_REGISTRY.queries) == {
        AuthenticateApiTokenQuery,
        AuthenticateSessionQuery,
        ListSessionsQuery,
        ProfileQuery,
        SecurityHistoryQuery,
        ListPersonalTokensQuery,
    }


def test_identity_registry_rejects_incomplete_or_ambiguous_bindings() -> None:
    with pytest.raises(RegistrationError, match="more than one"):
        HandlerRegistry(
            commands=[(LoginCommand, LoginHandler)] * 2,
            queries=[],
        )
    with pytest.raises(RegistrationError, match="required command"):
        HandlerRegistry(
            commands=[],
            queries=[],
            required_commands=[LoginCommand],
        )


def test_identity_dispatch_resolves_only_selected_handler() -> None:
    resolved: list[type[object]] = []

    class SelectedHandler:
        async def execute(self, command: LoginCommand) -> str:
            return command.user_name

    instances = {LoginHandler: SelectedHandler()}

    class Container:
        async def get(self, handler: type[object]) -> object:
            resolved.append(handler)
            return instances[handler]

    class UnknownQuery:
        pass

    async def run() -> None:
        dispatcher = IdentityModuleDispatcher(Container())
        command = LoginCommand("alice", "secret", None, None)
        assert await dispatcher.execute(command) == "alice"
        assert resolved == [LoginHandler]
        with pytest.raises(UnsupportedMessage, match="Unsupported query"):
            await dispatcher.query(UnknownQuery())
        assert resolved == [LoginHandler]

    asyncio.run(run())


def test_logout_dispatch_resolves_from_fresh_identity_action_scope() -> None:
    from dishka import Scope

    scopes = []
    resolutions = []
    events = []

    class LogoutActionHandler:
        async def execute(self, command: LogoutCommand) -> None:
            return None

    class ActionContainer:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, handler: type[object], component: str | None = None) -> object:
            resolutions.append((handler, component))
            if handler is SqlAlchemyUnitOfWork:

                class Unit:
                    async def run(self, action, materialize):
                        result = await action()
                        events.append("commit")
                        return materialize(result)

                return Unit()
            return LogoutActionHandler()

    class Container:
        async def get(self, handler: type[object]) -> object:
            raise AssertionError(f"non-action handler requested: {handler}")

        def __call__(self, *, scope: Scope) -> ActionContainer:
            scopes.append(scope)
            return ActionContainer()

    async def run() -> None:
        dispatcher = IdentityModuleDispatcher(Container())
        for _ in range(2):
            assert (
                await dispatcher.execute(LogoutCommand("token", "csrf", "https://portal.example"))
                is None
            )

    asyncio.run(run())
    assert scopes == [Scope.ACTION, Scope.ACTION]
    assert (
        resolutions
        == [
            (SqlAlchemyUnitOfWork, "identity_action"),
            (LogoutHandler, "identity_action"),
        ]
        * 2
    )
    assert events == ["commit", "commit"]


def test_bearer_query_uses_its_own_transaction_and_leaves_platform_unit_unused() -> None:
    now = datetime.now(UTC)
    events: list[str] = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def begin(self):
            events.append("begin")

        async def commit(self):
            events.append("commit")

        async def rollback(self):
            events.append("rollback")

        async def close(self):
            events.append("close")

    class Repository:
        def __init__(self, session):
            assert isinstance(session, Session)

        async def find_token_credential(self, digest):
            assert digest == "digest"
            return ApiTokenAuthenticationDetails(
                uuid4(),
                uuid4(),
                uuid4(),
                "developer",
                ("resources:read",),
                True,
                now + timedelta(hours=1),
                None,
            )

    class Hasher:
        def digest(self, token):
            return "digest"

    platform_unit = SqlAlchemyUnitOfWork(Session())
    operation = AuthenticateApiTokenHandler(
        SqlAlchemyApiTokenTransaction(lambda: Session(), lambda active: Repository(active)),
        Hasher(),
    )

    async def run() -> None:
        principal = await operation.execute(AuthenticateApiTokenQuery("t" * 43))
        assert principal.role == "developer"

    asyncio.run(run())
    assert events == ["begin", "commit", "close"]
    assert platform_unit._used is False

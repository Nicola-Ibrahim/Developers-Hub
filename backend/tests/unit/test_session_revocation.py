import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from dishka import Provider, Scope, make_async_container, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from composition.integrations.providers import IdentityActionIntegrationProvider
from identity.application.api_tokens.manage_personal_tokens import PersonalTokenHandler
from identity.application.authentication.authenticate_session.handler import (
    AuthenticateSessionHandler,
)
from identity.application.authentication.logout.command import LogoutCommand
from identity.application.authentication.logout.handler import LogoutHandler
from identity.application.interfaces.security import TokenGenerator, TokenHasher
from identity.application.sessions.list_sessions.handler import ListSessionsHandler
from identity.application.sessions.revoke_all_sessions.command import RevokeAllSessionsCommand
from identity.application.sessions.revoke_all_sessions.handler import RevokeAllSessionsHandler
from identity.application.sessions.revoke_session.command import RevokeSessionCommand
from identity.application.sessions.revoke_session.handler import RevokeSessionHandler
from identity.application.sessions.rotate_csrf.handler import RotateCsrfHandler
from identity.application.sessions.select_active_project.handler import SelectActiveProjectHandler
from identity.domain.aggregates.session import Session
from identity.domain.records import SessionPrincipal
from identity.domain.value_objects.session_expiry import SessionExpiry
from identity.infra.composition.action_provider import IdentityActionProvider
from identity.infra.composition.providers import IdentityTokenScopePolicy
from shared.infra.clock import Clock
from shared.infra.persistence.unit_of_work import SqlAlchemyUnitOfWork
from shared.infra.settings import Settings


def test_session_revocation_is_idempotent_and_keeps_first_timestamp() -> None:
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    revoked_at = created_at + timedelta(minutes=1)
    session = Session(
        uuid4(),
        uuid4(),
        created_at,
        created_at,
        SessionExpiry.from_login(created_at),
        None,
        1,
    )

    revoked = session.revoke(revoked_at)

    assert revoked.revoked_at == revoked_at
    assert revoked.revoke(revoked_at + timedelta(minutes=1)) is revoked


def test_revoke_handler_authorizes_and_persists_for_dispatch_transaction() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    user_id, session_id = uuid4(), uuid4()
    session = Session(
        session_id,
        user_id,
        now,
        now,
        SessionExpiry.from_login(now),
        None,
        1,
    )

    class Authorization:
        async def authorize_browser_operation(self, *args, **kwargs):
            return SessionPrincipal(user_id, "dev", uuid4(), None, None, None, (), (), "")

        async def validate_csrf(self, token_digest, csrf_digest):
            return token_digest == "session-digest" and csrf_digest == "csrf-digest"

        async def load_for_revocation(self, owner_id, target_id):
            assert (owner_id, target_id) == (user_id, session_id)
            return session

        async def save_revocation(self, revoked):
            self.saved = revoked

    repository = Authorization()
    handler = RevokeSessionHandler(
        repository,
        lambda: now,
        lambda value: f"{value}-digest",
        ("https://portal.example",),
    )

    assert asyncio.run(
        handler.execute(
            RevokeSessionCommand("session", session_id, "csrf", "https://portal.example")
        )
    )
    assert repository.saved.revoked_at == now


def test_logout_and_revoke_all_authorize_before_writing_in_unit_of_work() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    user_id = uuid4()
    calls: list[tuple[str, object]] = []

    class Authorization:
        async def authorize_browser_operation(self, *args, **kwargs):
            calls.append(("authorize", kwargs["lock_for_mutation"]))
            return SessionPrincipal(user_id, "dev", uuid4(), None, None, None, (), (), "")

        async def validate_csrf(self, token_digest, csrf_digest):
            calls.append(("csrf", (token_digest, csrf_digest)))
            return token_digest == "session-digest" and csrf_digest == "csrf-digest"

        async def logout(self, token_digest, time):
            calls.append(("logout", (token_digest, time)))

        async def logout_all(self, owner_id, time):
            calls.append(("logout_all", (owner_id, time)))
            return 3

    repository = Authorization()

    def digest(value):
        return f"{value}-digest"

    logout = LogoutHandler(repository, lambda: now, digest, ("https://portal.example",))
    revoke_all = RevokeAllSessionsHandler(
        repository, lambda: now, digest, ("https://portal.example",)
    )

    async def verify() -> None:
        assert (
            await logout.execute(LogoutCommand("session", "csrf", "https://portal.example")) is None
        )
        assert (
            await revoke_all.execute(
                RevokeAllSessionsCommand("session", "csrf", "https://portal.example")
            )
            == 3
        )

    asyncio.run(verify())
    assert calls == [
        ("authorize", True),
        ("csrf", ("session-digest", "csrf-digest")),
        ("logout", ("session-digest", now)),
        ("authorize", True),
        ("csrf", ("session-digest", "csrf-digest")),
        ("logout_all", (user_id, now)),
    ]


def test_identity_action_handlers_get_fresh_sessions_and_share_each_uow_session() -> None:
    created_sessions = []

    class FakeSession:
        async def close(self):
            return None

    class SessionFactory:
        def __call__(self):
            session = FakeSession()
            created_sessions.append(session)
            return session

    session_factory = SessionFactory()
    config = Settings(
        database_url="postgresql+psycopg://localhost:1/devops_hub_test", token_pepper="t" * 40
    )

    class Hasher:
        @staticmethod
        def digest(value: str) -> str:
            return value

    class RootProvider(Provider):
        @provide(scope=Scope.APP)
        def sessions(self) -> async_sessionmaker[AsyncSession]:
            return session_factory

        @provide(scope=Scope.APP)
        def clock(self) -> Clock:
            return lambda: datetime(2026, 1, 1, tzinfo=UTC)

        @provide(scope=Scope.APP)
        def hasher(self) -> TokenHasher:
            return Hasher()

        @provide(scope=Scope.APP)
        def generator(self) -> TokenGenerator:
            class Generator:
                def generate(self) -> str:
                    return "generated"

            return Generator()

        @provide(scope=Scope.APP)
        def settings(self) -> Settings:
            return config

        @provide(scope=Scope.APP)
        def token_scope_policy(self) -> IdentityTokenScopePolicy:
            return IdentityTokenScopePolicy(("catalog:read",))

    async def verify() -> None:
        container = make_async_container(
            RootProvider(),
            IdentityActionIntegrationProvider(component="identity_action"),
            IdentityActionProvider(component="identity_action"),
        )
        try:
            for handler_type in (
                LogoutHandler,
                RevokeAllSessionsHandler,
                RevokeSessionHandler,
                AuthenticateSessionHandler,
                ListSessionsHandler,
                RotateCsrfHandler,
                SelectActiveProjectHandler,
                PersonalTokenHandler,
            ):
                async with container(scope=Scope.ACTION) as action:
                    handler = await action.get(handler_type, component="identity_action")
                    session = created_sessions[-1]
                    unit = await action.get(SqlAlchemyUnitOfWork, component="identity_action")
                    if handler_type in (
                        LogoutHandler,
                        RevokeAllSessionsHandler,
                        RevokeSessionHandler,
                    ):
                        assert handler.sessions._session is session
                    elif handler_type is PersonalTokenHandler:
                        assert handler.sessions._session is session
                        assert handler.tokens._session is session
                    else:
                        assert handler.repository._session is session
                    assert unit.session is session
            assert len(created_sessions) == 8
            assert len({id(session) for session in created_sessions}) == 8
        finally:
            await container.close()

    asyncio.run(verify())

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from composition.container import BackendContainer
from identity.application.authentication.logout.command import LogoutCommand
from identity.application.authentication.logout.handler import LogoutHandler
from identity.application.sessions.revoke_all_sessions.command import RevokeAllSessionsCommand
from identity.application.sessions.revoke_all_sessions.handler import RevokeAllSessionsHandler
from identity.application.sessions.revoke_session.command import RevokeSessionCommand
from identity.application.sessions.revoke_session.handler import RevokeSessionHandler
from identity.domain.aggregates.session import Session
from identity.domain.records import SessionPrincipal
from identity.domain.value_objects.session_expiry import SessionExpiry
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


def test_revoke_handler_authorizes_and_persists_in_one_unit_of_work() -> None:
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

    class Revocations:
        async def load_for_revocation(self, owner_id, target_id):
            assert (owner_id, target_id) == (user_id, session_id)
            return session

        async def save_revocation(self, revoked):
            self.saved = revoked

    class UnitOfWork:
        async def run(self, action, materialize):
            self.calls = getattr(self, "calls", 0) + 1
            return materialize(await action())

    authorization, revocations, unit = Authorization(), Revocations(), UnitOfWork()
    handler = RevokeSessionHandler(
        authorization,
        revocations,
        unit,
        lambda: now,
        lambda value: f"{value}-digest",
        ("https://portal.example",),
    )

    assert asyncio.run(
        handler.execute(
            RevokeSessionCommand("session", session_id, "csrf", "https://portal.example")
        )
    )
    assert unit.calls == 1
    assert revocations.saved.revoked_at == now


def test_revoke_handler_repositories_and_uow_share_request_session() -> None:
    config = Settings(
        database_url="postgresql+psycopg://localhost:1/devops_hub_test", token_pepper="t" * 40
    )
    container = BackendContainer(config).combined()

    async def verify() -> None:
        try:
            async with container() as scope:
                handler = await scope.get(RevokeSessionHandler)
                logout = await scope.get(LogoutHandler)
                revoke_all = await scope.get(RevokeAllSessionsHandler)
                session = await scope.get(AsyncSession)
                assert handler.authorization._session is session
                assert handler.revocations._session is session
                assert handler.unit._unit.session is session
                for operation in (logout, revoke_all):
                    assert operation.authorization._session is session
                    assert operation.sessions._session is session
                    assert operation.unit._unit.session is session
                await session.close()
        finally:
            await container.close()

    asyncio.run(verify())


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

    class Sessions:
        async def logout(self, token_digest, time):
            calls.append(("logout", (token_digest, time)))

        async def logout_all(self, owner_id, time):
            calls.append(("logout_all", (owner_id, time)))
            return 3

    class Unit:
        async def run(self, action, materialize):
            calls.append(("begin", None))
            return materialize(await action())

    authorization, sessions, unit = Authorization(), Sessions(), Unit()

    def digest(value):
        return f"{value}-digest"

    logout = LogoutHandler(
        authorization, sessions, unit, lambda: now, digest, ("https://portal.example",)
    )
    revoke_all = RevokeAllSessionsHandler(
        authorization, sessions, unit, lambda: now, digest, ("https://portal.example",)
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
        ("begin", None),
        ("authorize", True),
        ("csrf", ("session-digest", "csrf-digest")),
        ("logout", ("session-digest", now)),
        ("begin", None),
        ("authorize", True),
        ("csrf", ("session-digest", "csrf-digest")),
        ("logout_all", (user_id, now)),
    ]

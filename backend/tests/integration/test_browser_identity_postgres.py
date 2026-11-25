"""Real PostgreSQL verification for durable browser authentication and recovery."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Session
from test_foundation_postgres import async_engine_for

from composition.integrations.project_access_persistence import (
    SqlAlchemyIdentityProjectAccess,
    identity_repositories_for_session,
    project_access_repository_for_session,
)
from devops_platform.domain.value_objects.project_role import ProjectRole
from devops_platform.infra.persistence.models.project_access import ProjectMembershipRow, ProjectRow
from identity.application.accounts.complete_password_setup.command import (
    CompletePasswordSetupCommand,
)
from identity.application.accounts.complete_password_setup.handler import (
    CompletePasswordSetupHandler,
)
from identity.application.accounts.create_user.command import CreateUserCommand
from identity.application.accounts.create_user.handler import CreateUserHandler
from identity.application.accounts.set_user_status.command import SetUserStatusCommand
from identity.application.accounts.set_user_status.handler import SetUserStatusHandler
from identity.application.accounts.start_password_setup.command import StartPasswordSetupCommand
from identity.application.accounts.start_password_setup.handler import StartPasswordSetupHandler
from identity.application.authentication.authenticate_session.handler import (
    AuthenticateSessionHandler,
)
from identity.application.authentication.authenticate_session.query import AuthenticateSessionQuery
from identity.application.authentication.login.command import LoginCommand
from identity.application.authentication.login.handler import LoginHandler
from identity.application.authentication.logout.command import LogoutCommand
from identity.application.authentication.logout.handler import LogoutHandler
from identity.application.sessions.rotate_csrf.command import RotateCsrfCommand
from identity.application.sessions.rotate_csrf.handler import RotateCsrfHandler
from identity.domain.errors import IdentityValidationError
from identity.domain.session_errors import SessionAuthenticationRejected
from identity.infra.composition.identity_transactions import SqlAlchemyIdentityTransaction
from identity.infra.persistence.models.activity import IdentityActivityRow
from identity.infra.persistence.models.session import (
    LoginThrottleRow,
    SessionRow,
)
from identity.infra.persistence.models.user import InternalUserRow, PasswordSetupRow
from identity.infra.security.jwt import JwtSessionTokens
from identity.infra.security.opaque_secrets import PepperedTokenHasher, SecureTokenGenerator
from identity.infra.security.passwords import Argon2idPasswordHasher
from shared.infra.persistence.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.postgres

PEPPER = "browser-test-pepper-" * 3
ORIGIN = "http://localhost:3000"
PASSWORD = "local-safe-test-password"


def test_deactivation_and_role_change_cannot_remove_both_admins(postgres_engine):
    first_admin, project_id, _ = seed_user(postgres_engine)
    second_admin = uuid4()
    with Session(postgres_engine) as session, session.begin():
        session.add(InternalUserRow(id=second_admin, name=f"admin-{second_admin}", active=True))
        session.flush()
        session.add(ProjectMembershipRow(user_id=second_admin, project_id=project_id, role="admin"))

    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    identity = IdentityFixture(sessions, lambda: datetime.now(UTC))

    async def exercise():
        try:
            return await asyncio.wait_for(
                asyncio.gather(
                    identity.execute(SetUserStatusCommand(second_admin, first_admin, False)),
                    identity.set_membership(first_admin, second_admin, project_id, "developer"),
                    return_exceptions=True,
                ),
                timeout=10,
            )
        finally:
            await database.dispose()

    results = asyncio.run(exercise())
    assert results.count(None) == 1, results
    assert all(
        result is None
        or isinstance(result, (SessionAuthenticationRejected, IdentityValidationError))
        for result in results
    ), results
    with Session(postgres_engine) as session:
        assert any(
            session.get(InternalUserRow, admin_id).active
            and session.get(ProjectMembershipRow, (admin_id, project_id)).role == "admin"
            for admin_id in (first_admin, second_admin)
        )


class IdentityFixture:
    def __init__(self, sessions, clock):
        self.sessions = sessions
        self.clock = clock
        transaction = SqlAlchemyIdentityTransaction(sessions, identity_repositories_for_session)
        passwords = Argon2idPasswordHasher()
        tokens = SecureTokenGenerator()
        hasher = PepperedTokenHasher(PEPPER)
        digest = hasher.digest
        self.digest = digest
        self.handlers = {
            LoginCommand: LoginHandler(
                transaction,
                passwords,
                tokens,
                hasher,
                JwtSessionTokens(PEPPER),
            ),
            CreateUserCommand: CreateUserHandler(transaction, passwords),
            SetUserStatusCommand: SetUserStatusHandler(transaction),
            StartPasswordSetupCommand: StartPasswordSetupHandler(transaction, tokens, hasher),
            CompletePasswordSetupCommand: CompletePasswordSetupHandler(
                transaction, passwords, hasher
            ),
            AuthenticateSessionQuery: self._action_handler(
                lambda _users, repository: AuthenticateSessionHandler(repository, hasher)
            ),
            RotateCsrfCommand: self._action_handler(
                lambda _users, repository: RotateCsrfHandler(repository, hasher, tokens)
            ),
            LogoutCommand: self._action_handler(
                lambda _users, repository: LogoutHandler(repository, hasher, (ORIGIN,))
            ),
        }

    def _action_handler(self, build_handler):
        fixture = self

        class Action:
            async def execute(self, command):
                session = fixture.sessions()
                users, repository = identity_repositories_for_session(session)
                handler = build_handler(users, repository)
                return await SqlAlchemyUnitOfWork(session).run(
                    lambda: handler.execute(command), lambda result: result
                )

        return Action()

    async def execute(self, message):
        return await self.handlers[type(message)].execute(message)

    async def set_membership(self, actor_id, user_id, project_id, role):
        async with self.sessions() as session, session.begin():
            validated_role = ProjectRole.parse(role).value if role is not None else None
            await project_access_repository_for_session(session).set_membership(
                actor_id=actor_id,
                user_id=user_id,
                project_id=project_id,
                role=validated_role,
                now=self.clock(),
            )

    async def list_project_members(self, actor_id, project_id):
        async with self.sessions() as session, session.begin():
            return await project_access_repository_for_session(session).list_project_members(
                actor_id=actor_id, project_id=project_id
            )


def perform_login(identity, user_name, password, project_id):
    return identity.execute(LoginCommand(user_name, password, project_id))


def seed_user(engine, role="admin"):
    user_id, project_id = uuid4(), uuid4()
    user = InternalUserRow(
        id=user_id,
        name=f"operator-{user_id}",
        active=True,
        password_hash=Argon2idPasswordHasher().hash(PASSWORD),
        credential_version=1,
    )
    user_name = user.name
    project = ProjectRow(id=project_id, name=f"project-{project_id}")
    with Session(engine) as session, session.begin():
        session.add_all([user, project])
        session.flush()
        session.add(ProjectMembershipRow(user_id=user_id, project_id=project_id, role=role))
    return user_id, project_id, user_name


def test_login_upgrades_legacy_password_without_changing_credential_version(postgres_engine):
    user_id, project_id, user_name = seed_user(postgres_engine)
    salt = bytes(range(16))
    encoded = hashlib.scrypt(PASSWORD.encode(), salt=salt, n=1 << 14, r=8, p=1, dklen=32)
    with Session(postgres_engine) as session, session.begin():
        user = session.get(InternalUserRow, user_id)
        assert user is not None
        user.password_hash = f"scrypt${1 << 14}$8$1${salt.hex()}${encoded.hex()}"
        version = user.credential_version

    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    identity = IdentityFixture(sessions, lambda: datetime.now(UTC))

    async def exercise():
        try:
            result = await perform_login(identity, user_name, PASSWORD, project_id)
            assert result.principal.user_id == user_id
        finally:
            await database.dispose()

    asyncio.run(exercise())
    with Session(postgres_engine) as session:
        user = session.get(InternalUserRow, user_id)
        assert user is not None and user.password_hash is not None
        assert user.password_hash.startswith("$argon2id$")
        assert user.credential_version == version


def test_password_change_during_login_verification_blocks_stale_session(postgres_engine):
    user_id, project_id, user_name = seed_user(postgres_engine)
    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    identity = IdentityFixture(sessions, lambda: datetime.now(UTC))

    async def exercise():
        loop = asyncio.get_running_loop()
        verification_started = asyncio.Event()
        release_verification = Event()

        class PausedHasher(Argon2idPasswordHasher):
            def verify(self, password: str, encoded: str | None) -> bool:
                loop.call_soon_threadsafe(verification_started.set)
                assert release_verification.wait(10)
                return super().verify(password, encoded)

        identity.handlers[LoginCommand].passwords = PausedHasher()
        login = asyncio.create_task(
            perform_login(identity, user_name, PASSWORD, project_id)
        )
        try:
            try:
                await asyncio.wait_for(verification_started.wait(), 5)
                async with asyncio.timeout(5):
                    setup = await identity.execute(StartPasswordSetupCommand(user_id, user_id))
                    await identity.execute(
                        CompletePasswordSetupCommand(setup, "a-different-valid-password")
                    )
            finally:
                release_verification.set()
                with pytest.raises(SessionAuthenticationRejected):
                    await asyncio.wait_for(login, 5)
        finally:
            await database.dispose()

    asyncio.run(exercise())
    with Session(postgres_engine) as session:
        assert (
            session.scalar(
                select(func.count()).select_from(SessionRow).where(SessionRow.user_id == user_id)
            )
            == 0
        )


def test_browser_session_survives_service_restart_and_revokes_on_password_reset(postgres_engine):
    user_id, project_id, user_name = seed_user(postgres_engine)
    database = async_engine_for(postgres_engine)
    now = datetime.now(UTC)
    current_time = [now]
    sessions = async_sessionmaker(database, expire_on_commit=False)
    first_service = IdentityFixture(sessions, lambda: current_time[0])

    async def exercise():
        login = await perform_login(first_service, user_name, PASSWORD, project_id)
        assert login.principal.user_id == user_id
        assert login.principal.role == "admin"
        assert login.session_token not in repr(login)
        with pytest.raises(IdentityValidationError):
            await first_service.set_membership(user_id, user_id, project_id, "developer")
        await first_service.execute(AuthenticateSessionQuery(login.session_token, project_id))
        members = await first_service.list_project_members(user_id, project_id)
        assert len(members) == 1 and members[0][0] == user_id
        added_id = await first_service.execute(
            CreateUserCommand(f"member-{uuid4()}", "a-different-safe-password", user_id)
        )
        await first_service.set_membership(user_id, added_id, project_id, "developer")
        await first_service.execute(AuthenticateSessionQuery(login.session_token, project_id))
        members = await first_service.list_project_members(user_id, project_id)
        assert {member[0] for member in members} == {user_id, added_id}

        # A newly composed service can authenticate the digest persisted by the first.
        restarted = IdentityFixture(sessions, lambda: current_time[0])
        principal = await restarted.execute(AuthenticateSessionQuery(login.session_token))
        assert principal.session_id == login.principal.session_id
        assert principal.project_id == project_id

        current = await restarted.execute(RotateCsrfCommand(login.session_token))
        with pytest.raises(SessionAuthenticationRejected):
            await restarted.execute(LogoutCommand(login.session_token, login.csrf_token, ORIGIN))
        await restarted.execute(LogoutCommand(login.session_token, current.csrf_token, ORIGIN))
        with pytest.raises(SessionAuthenticationRejected):
            await restarted.execute(AuthenticateSessionQuery(login.session_token))

        login = await perform_login(restarted, user_name, PASSWORD, project_id)
        reset = await restarted.execute(StartPasswordSetupCommand(user_id, user_id))
        assert await restarted.execute(
            CompletePasswordSetupCommand(reset, "new-local-safe-password")
        )
        assert not await restarted.execute(
            CompletePasswordSetupCommand(reset, "another-local-safe-password")
        )
        with pytest.raises(SessionAuthenticationRejected):
            await restarted.execute(AuthenticateSessionQuery(login.session_token))
        changed = await perform_login(
            restarted, user_name, "new-local-safe-password", project_id
        )
        assert changed.principal.user_id == user_id

        with Session(postgres_engine) as session:
            stored = session.query(SessionRow).filter_by(id=changed.principal.session_id).one()
            throttle = session.get(LoginThrottleRow, restarted.digest(user_name))
            assert stored.token_digest != changed.session_token
            assert stored.csrf_digest != changed.csrf_token
            assert throttle is not None and throttle.failures == 0
            assert session.query(IdentityActivityRow).filter_by(subject_id=user_id).count() >= 4

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(database.dispose())


def test_concurrent_password_setup_issuers_leave_one_setup_active(postgres_engine):
    user_id, _project_id, _user_name = seed_user(postgres_engine)
    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    service = IdentityFixture(sessions, lambda: datetime.now(UTC))

    async def exercise():
        try:
            secrets = await asyncio.wait_for(
                asyncio.gather(
                    service.execute(StartPasswordSetupCommand(user_id, user_id)),
                    service.execute(StartPasswordSetupCommand(user_id, user_id)),
                ),
                timeout=10,
            )
            return secrets
        finally:
            await database.dispose()

    issued_secrets = asyncio.run(exercise())
    digests = {service.digest(secret) for secret in issued_secrets}
    with Session(postgres_engine) as session:
        setups = session.scalars(
            select(PasswordSetupRow).where(PasswordSetupRow.user_id == user_id)
        ).all()
        active = [setup for setup in setups if setup.consumed_at is None]
        assert len(setups) == 2
        assert len(active) == 1
        assert active[0].digest in digests
        assert (
            session.scalar(
                select(func.count())
                .select_from(IdentityActivityRow)
                .where(
                    IdentityActivityRow.subject_id == user_id,
                    IdentityActivityRow.action == "password_setup_issued",
                )
            )
            == 2
        )


def test_password_setup_consume_racing_new_setup_invalidation_is_serialized(postgres_engine):
    user_id, _project_id, _user_name = seed_user(postgres_engine)
    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    service = IdentityFixture(sessions, lambda: datetime.now(UTC))
    old_secret = asyncio.run(service.execute(StartPasswordSetupCommand(user_id, user_id)))
    with Session(postgres_engine) as session:
        original_hash = session.get(InternalUserRow, user_id).password_hash
    replacement_password = "concurrent-setup-replacement-password"

    async def exercise():
        try:
            return await asyncio.wait_for(
                asyncio.gather(
                    service.execute(CompletePasswordSetupCommand(old_secret, replacement_password)),
                    service.execute(StartPasswordSetupCommand(user_id, user_id)),
                ),
                timeout=10,
            )
        finally:
            await database.dispose()

    consumed, new_secret = asyncio.run(exercise())
    with Session(postgres_engine) as session:
        setups = session.scalars(
            select(PasswordSetupRow).where(PasswordSetupRow.user_id == user_id)
        ).all()
        old_setup = next(setup for setup in setups if setup.digest == service.digest(old_secret))
        active = [setup for setup in setups if setup.consumed_at is None]
        user = session.get(InternalUserRow, user_id)
        consume_audits = session.scalar(
            select(func.count())
            .select_from(IdentityActivityRow)
            .where(
                IdentityActivityRow.subject_id == user_id,
                IdentityActivityRow.action == "password_setup_consumed",
            )
        )
        assert old_setup.consumed_at is not None
        assert len(active) == 1
        assert active[0].digest == service.digest(new_secret)
        if consumed:
            assert user.password_hash != original_hash
        else:
            assert user.password_hash == original_hash
        assert consume_audits == int(consumed)


def test_password_setup_credential_stays_invalid_after_user_disable_and_reenable(postgres_engine):
    user_id, _project_id, _user_name = seed_user(postgres_engine, role="developer")
    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    service = IdentityFixture(sessions, lambda: datetime.now(UTC))
    with Session(postgres_engine) as session:
        original_hash = session.get(InternalUserRow, user_id).password_hash

    async def exercise():
        try:
            secret = await service.execute(StartPasswordSetupCommand(user_id, user_id))
            await service.execute(SetUserStatusCommand(user_id, user_id, False))
            await service.execute(SetUserStatusCommand(user_id, user_id, True))
            assert not await service.execute(
                CompletePasswordSetupCommand(secret, "stale-setup-credential-password")
            )
            return secret
        finally:
            await database.dispose()

    secret = asyncio.run(exercise())
    with Session(postgres_engine) as session:
        setup = session.scalar(
            select(PasswordSetupRow).where(
                PasswordSetupRow.user_id == user_id,
                PasswordSetupRow.digest == service.digest(secret),
            )
        )
        user = session.get(InternalUserRow, user_id)
        assert user.active
        assert user.password_hash == original_hash
        assert setup is not None and setup.consumed_at is not None


def test_persistent_username_throttle_blocks_retries_without_revealing_account(postgres_engine):
    _user_id, _project_id, user_name = seed_user(postgres_engine, role="developer")
    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    service = IdentityFixture(sessions, lambda: datetime.now(UTC))

    async def exercise():
        for _ in range(6):
            with pytest.raises(SessionAuthenticationRejected):
                await perform_login(service, user_name, "incorrect password", None)
        # The correct password remains blocked during the persisted lockout interval.
        with pytest.raises(SessionAuthenticationRejected):
            await perform_login(service, user_name, PASSWORD, None)
        with Session(postgres_engine) as session:
            throttle = session.get(LoginThrottleRow, service.digest(user_name))
            assert throttle is not None
            assert throttle.failures == 6
            assert throttle.locked_until is not None
            assert session.query(SessionRow).count() == 0

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(database.dispose())


def test_session_idle_and_absolute_expiry_and_disabled_user_rejection(postgres_engine):
    user_id, project_id, user_name = seed_user(postgres_engine, role="developer")
    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    service = IdentityFixture(sessions, lambda: datetime.now(UTC))

    async def exercise():
        login = await perform_login(service, user_name, PASSWORD, project_id)
        with Session(postgres_engine) as session, session.begin():
            stored = session.get(SessionRow, login.principal.session_id)
            assert stored is not None
            stored.idle_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        with pytest.raises(SessionAuthenticationRejected):
            await service.execute(AuthenticateSessionQuery(login.session_token))

        login = await perform_login(service, user_name, PASSWORD, project_id)
        with Session(postgres_engine) as session, session.begin():
            stored = session.get(SessionRow, login.principal.session_id)
            assert stored is not None
            stored.absolute_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        with pytest.raises(SessionAuthenticationRejected):
            await service.execute(AuthenticateSessionQuery(login.session_token))

        login = await perform_login(service, user_name, PASSWORD, project_id)
        await service.execute(SetUserStatusCommand(user_id, user_id, False))
        with pytest.raises(SessionAuthenticationRejected):
            await service.execute(AuthenticateSessionQuery(login.session_token))

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(database.dispose())


def test_authorized_browser_activity_refreshes_idle_expiry(postgres_engine):
    _user_id, project_id, user_name = seed_user(postgres_engine)
    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    service = IdentityFixture(sessions, lambda: datetime.now(UTC))

    async def exercise():
        login = await perform_login(service, user_name, PASSWORD, project_id)
        before_authentication = datetime.now(UTC)
        with Session(postgres_engine) as session, session.begin():
            stored = session.get(SessionRow, login.principal.session_id)
            assert stored is not None
            stored.last_seen_at = before_authentication - timedelta(minutes=20)
            stored.idle_expires_at = before_authentication + timedelta(minutes=10)
        await service.execute(AuthenticateSessionQuery(login.session_token, project_id))
        members = await service.list_project_members(_user_id, project_id)
        assert len(members) == 1

        with Session(postgres_engine) as session:
            stored = session.get(SessionRow, login.principal.session_id)
            assert stored is not None
            assert stored.last_seen_at >= before_authentication
            assert stored.idle_expires_at == stored.last_seen_at + timedelta(minutes=30)

        # Activity at minute 20 keeps the session usable after its original
        # minute-30 idle deadline while the absolute expiry stays unchanged.
        with Session(postgres_engine) as session, session.begin():
            stored = session.get(SessionRow, login.principal.session_id)
            assert stored is not None
            stored.last_seen_at -= timedelta(minutes=20)
        assert (
            await service.execute(AuthenticateSessionQuery(login.session_token))
        ).user_id == _user_id

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(database.dispose())


def test_membership_update_and_session_authorization_share_lock_order(postgres_engine):
    user_id, project_id, user_name = seed_user(postgres_engine)
    second_admin_id = uuid4()
    with Session(postgres_engine) as session, session.begin():
        session.add(
            InternalUserRow(
                id=second_admin_id,
                name=f"second-admin-{second_admin_id}",
                active=True,
                password_hash=Argon2idPasswordHasher().hash("another-safe-test-password"),
                credential_version=1,
            )
        )
        session.flush()
        session.add(
            ProjectMembershipRow(user_id=second_admin_id, project_id=project_id, role="admin")
        )

    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    service = IdentityFixture(sessions, lambda: datetime.now(UTC))

    async def exercise():
        login = await perform_login(service, user_name, PASSWORD, project_id)
        digest = service.digest(login.session_token)

        async def authorize():
            async with sessions() as session, session.begin():
                _users, repository = identity_repositories_for_session(session)
                principal = await repository.authorize_session_operation(
                    digest, project_id, datetime.now(UTC)
                )
                assert principal is not None

        async def update_membership(role: str):
            await service.set_membership(second_admin_id, user_id, project_id, role)

        # Repeated simultaneous reads and membership writes would form a
        # user/project lock cycle if authorization acquired session/user first.
        for index in range(12):
            await asyncio.wait_for(
                asyncio.gather(
                    authorize(), update_membership("developer" if index % 2 == 0 else "admin")
                ),
                timeout=10,
            )

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(database.dispose())


@pytest.mark.parametrize("operation", ["authorize", "select_project"])
def test_revocation_during_authority_lock_wait_is_revalidated(
    postgres_engine, operation, monkeypatch
):
    _user_id, project_id, user_name = seed_user(postgres_engine)
    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    service = IdentityFixture(sessions, lambda: datetime.now(UTC))

    async def exercise():
        login = await perform_login(service, user_name, PASSWORD, project_id)
        digest = service.digest(login.session_token)
        discovered, resume = asyncio.Event(), asyncio.Event()

        async def authorize():
            async with sessions() as session, session.begin():
                _users, repository = identity_repositories_for_session(session)
                original = SqlAlchemyIdentityProjectAccess.lock_user_project_access

                async def paused_lookup(project_access, user_id, additional_project_ids=()):
                    if project_access._session is session:
                        discovered.set()
                        await resume.wait()
                    return await original(project_access, user_id, additional_project_ids)

                monkeypatch.setattr(
                    SqlAlchemyIdentityProjectAccess,
                    "lock_user_project_access",
                    paused_lookup,
                )
                if operation == "authorize":
                    return await repository.authorize_session_operation(
                        digest, project_id, datetime.now(UTC)
                    )
                return await repository.select_project(
                    token_digest=digest, project_id=project_id, now=datetime.now(UTC)
                )

        pending = asyncio.create_task(authorize())
        await asyncio.wait_for(discovered.wait(), timeout=5)
        try:
            await asyncio.wait_for(
                service.execute(LogoutCommand(login.session_token, login.csrf_token, ORIGIN)),
                timeout=5,
            )
        finally:
            resume.set()
        assert await asyncio.wait_for(pending, timeout=5) is None

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(database.dispose())

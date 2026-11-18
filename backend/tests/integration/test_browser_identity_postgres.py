"""Real PostgreSQL verification for durable browser authentication and recovery."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Session
from test_foundation_postgres import async_engine_for

from composition.integrations.project_access import ProjectAccessApplicationBridge
from composition.integrations.project_access_persistence import identity_repository_for_session
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
from identity.application.project_access.list_project_members.handler import (
    ListProjectMembersHandler,
)
from identity.application.project_access.list_project_members.query import ListProjectMembersQuery
from identity.application.project_access.manage_project_membership.command import (
    SetProjectMembershipCommand,
)
from identity.application.project_access.manage_project_membership.handler import (
    SetProjectMembershipHandler,
)
from identity.application.sessions.rotate_csrf.command import RotateCsrfCommand
from identity.application.sessions.rotate_csrf.handler import RotateCsrfHandler
from identity.domain.browser_errors import BrowserAuthenticationRejected
from identity.domain.errors import IdentityValidationError
from identity.infra.composition.browser_transactions import SqlAlchemyIdentityTransaction
from identity.infra.persistence.models.activity import IdentityActivityRow
from identity.infra.persistence.models.session import (
    BrowserLoginThrottleRow,
    BrowserSessionRow,
)
from identity.infra.persistence.models.user import InternalUserRow
from identity.infra.persistence.repositories.accounts_sessions import SQLAlchemyIdentityRepository
from identity.infra.security.browser_tokens import JwtBrowserSessionTokens
from identity.infra.security.login_verifier import LoginCredentialVerifier
from identity.infra.security.passwords import ScryptPasswordHasher
from identity.infra.security.tokens import PepperedTokenHasher, SecureTokenGenerator

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
                    identity.execute(
                        SetProjectMembershipCommand(
                            first_admin, second_admin, project_id, "developer"
                        )
                    ),
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
        or isinstance(result, (BrowserAuthenticationRejected, IdentityValidationError))
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
        transaction = SqlAlchemyIdentityTransaction(sessions, identity_repository_for_session)
        passwords = ScryptPasswordHasher()
        tokens = SecureTokenGenerator()
        digest = PepperedTokenHasher(PEPPER).digest
        self.digest = digest
        self.handlers = {
            LoginCommand: LoginHandler(
                transaction,
                LoginCredentialVerifier(passwords),
                tokens,
                clock,
                digest,
                (ORIGIN,),
                JwtBrowserSessionTokens(PEPPER),
            ),
            CreateUserCommand: CreateUserHandler(transaction, passwords, clock),
            SetUserStatusCommand: SetUserStatusHandler(transaction, clock),
            StartPasswordSetupCommand: StartPasswordSetupHandler(
                transaction, clock, tokens.generate, digest
            ),
            CompletePasswordSetupCommand: CompletePasswordSetupHandler(
                transaction, passwords, clock, digest
            ),
            SetProjectMembershipCommand: SetProjectMembershipHandler(
                transaction, ProjectAccessApplicationBridge(), clock
            ),
            ListProjectMembersQuery: ListProjectMembersHandler(
                transaction, ProjectAccessApplicationBridge(), clock, digest
            ),
            AuthenticateSessionQuery: AuthenticateSessionHandler(transaction, clock, digest),
            RotateCsrfCommand: RotateCsrfHandler(transaction, clock, digest, tokens.generate),
            LogoutCommand: LogoutHandler(transaction, clock, digest, (ORIGIN,)),
        }

    async def execute(self, message):
        return await self.handlers[type(message)].execute(message)


def perform_login(identity, user_name, password, project_id, origin):
    return identity.execute(LoginCommand(user_name, password, project_id, origin))


def seed_user(engine, role="admin"):
    user_id, project_id = uuid4(), uuid4()
    user = InternalUserRow(
        id=user_id,
        name=f"operator-{user_id}",
        active=True,
        password_hash=ScryptPasswordHasher().hash(PASSWORD),
        credential_version=1,
    )
    user_name = user.name
    project = ProjectRow(id=project_id, name=f"project-{project_id}")
    with Session(engine) as session, session.begin():
        session.add_all([user, project])
        session.flush()
        session.add(ProjectMembershipRow(user_id=user_id, project_id=project_id, role=role))
    return user_id, project_id, user_name


def test_browser_session_survives_service_restart_and_revokes_on_password_reset(postgres_engine):
    user_id, project_id, user_name = seed_user(postgres_engine)
    database = async_engine_for(postgres_engine)
    now = datetime(2026, 11, 1, tzinfo=UTC)
    current_time = [now]
    sessions = async_sessionmaker(database, expire_on_commit=False)
    first_service = IdentityFixture(sessions, lambda: current_time[0])

    async def exercise():
        login = await perform_login(first_service, user_name, PASSWORD, project_id, ORIGIN)
        assert login.principal.user_id == user_id
        assert login.principal.role == "admin"
        assert login.session_token not in repr(login)
        with pytest.raises(IdentityValidationError):
            await first_service.execute(
                SetProjectMembershipCommand(user_id, user_id, project_id, "developer")
            )
        members = await first_service.execute(
            ListProjectMembersQuery(login.session_token, project_id)
        )
        assert len(members) == 1 and members[0].user_id == user_id
        added_id = await first_service.execute(
            CreateUserCommand(f"member-{uuid4()}", "a-different-safe-password", user_id)
        )
        await first_service.execute(
            SetProjectMembershipCommand(user_id, added_id, project_id, "developer")
        )
        members = await first_service.execute(
            ListProjectMembersQuery(login.session_token, project_id)
        )
        assert {member.user_id for member in members} == {user_id, added_id}

        # A newly composed service can authenticate the digest persisted by the first.
        restarted = IdentityFixture(sessions, lambda: current_time[0])
        principal = await restarted.execute(AuthenticateSessionQuery(login.session_token))
        assert principal.session_id == login.principal.session_id
        assert principal.project_id == project_id

        current = await restarted.execute(RotateCsrfCommand(login.session_token))
        with pytest.raises(BrowserAuthenticationRejected):
            await restarted.execute(LogoutCommand(login.session_token, login.csrf_token, ORIGIN))
        await restarted.execute(LogoutCommand(login.session_token, current.csrf_token, ORIGIN))
        with pytest.raises(BrowserAuthenticationRejected):
            await restarted.execute(AuthenticateSessionQuery(login.session_token))

        login = await perform_login(restarted, user_name, PASSWORD, project_id, ORIGIN)
        reset = await restarted.execute(StartPasswordSetupCommand(user_id, user_id))
        assert await restarted.execute(
            CompletePasswordSetupCommand(reset, "new-local-safe-password")
        )
        assert not await restarted.execute(
            CompletePasswordSetupCommand(reset, "another-local-safe-password")
        )
        with pytest.raises(BrowserAuthenticationRejected):
            await restarted.execute(AuthenticateSessionQuery(login.session_token))
        changed = await perform_login(
            restarted, user_name, "new-local-safe-password", project_id, ORIGIN
        )
        assert changed.principal.user_id == user_id

        with Session(postgres_engine) as session:
            stored = (
                session.query(BrowserSessionRow).filter_by(id=changed.principal.session_id).one()
            )
            throttle = session.get(BrowserLoginThrottleRow, restarted.digest(user_name))
            assert stored.token_digest != changed.session_token
            assert stored.csrf_digest != changed.csrf_token
            assert throttle is not None and throttle.failures == 0
            assert session.query(IdentityActivityRow).filter_by(subject_id=user_id).count() >= 4

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(database.dispose())


def test_persistent_username_throttle_blocks_retries_without_revealing_account(postgres_engine):
    _user_id, _project_id, user_name = seed_user(postgres_engine, role="developer")
    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    service = IdentityFixture(sessions, lambda: datetime.now(UTC))

    async def exercise():
        for _ in range(6):
            with pytest.raises(BrowserAuthenticationRejected):
                await perform_login(service, user_name, "incorrect password", None, ORIGIN)
        # The correct password remains blocked during the persisted lockout interval.
        with pytest.raises(BrowserAuthenticationRejected):
            await perform_login(service, user_name, PASSWORD, None, ORIGIN)
        with Session(postgres_engine) as session:
            throttle = session.get(BrowserLoginThrottleRow, service.digest(user_name))
            assert throttle is not None
            assert throttle.failures == 6
            assert throttle.locked_until is not None
            assert session.query(BrowserSessionRow).count() == 0

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(database.dispose())


def test_session_idle_and_absolute_expiry_and_disabled_user_rejection(postgres_engine):
    user_id, project_id, user_name = seed_user(postgres_engine, role="developer")
    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    now = [datetime(2026, 11, 1, tzinfo=UTC)]
    service = IdentityFixture(sessions, lambda: now[0])

    async def exercise():
        login = await perform_login(service, user_name, PASSWORD, project_id, ORIGIN)
        now[0] += timedelta(minutes=31)
        with pytest.raises(BrowserAuthenticationRejected):
            await service.execute(AuthenticateSessionQuery(login.session_token))

        now[0] = datetime(2026, 11, 1, tzinfo=UTC)
        login = await perform_login(service, user_name, PASSWORD, project_id, ORIGIN)
        now[0] += timedelta(hours=8, seconds=1)
        with pytest.raises(BrowserAuthenticationRejected):
            await service.execute(AuthenticateSessionQuery(login.session_token))

        now[0] = datetime(2026, 11, 1, tzinfo=UTC)
        login = await perform_login(service, user_name, PASSWORD, project_id, ORIGIN)
        await service.execute(SetUserStatusCommand(user_id, user_id, False))
        with pytest.raises(BrowserAuthenticationRejected):
            await service.execute(AuthenticateSessionQuery(login.session_token))

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(database.dispose())


def test_authorized_browser_activity_refreshes_idle_expiry(postgres_engine):
    _user_id, project_id, user_name = seed_user(postgres_engine)
    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    now = [datetime(2026, 11, 1, tzinfo=UTC)]
    service = IdentityFixture(sessions, lambda: now[0])

    async def exercise():
        login = await perform_login(service, user_name, PASSWORD, project_id, ORIGIN)
        now[0] += timedelta(minutes=20)
        members = await service.execute(ListProjectMembersQuery(login.session_token, project_id))
        assert len(members) == 1

        with Session(postgres_engine) as session:
            stored = session.get(BrowserSessionRow, login.principal.session_id)
            assert stored is not None
            assert stored.last_seen_at == now[0]
            assert stored.idle_expires_at == now[0] + timedelta(minutes=30)

        # Activity at minute 20 keeps the session usable after its original
        # minute-30 idle deadline while the absolute expiry stays unchanged.
        now[0] += timedelta(minutes=20)
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
                password_hash=ScryptPasswordHasher().hash("another-safe-test-password"),
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
        login = await perform_login(service, user_name, PASSWORD, project_id, ORIGIN)
        digest = service.digest(login.session_token)

        async def authorize():
            async with sessions() as session, session.begin():
                principal = await SQLAlchemyIdentityRepository(session).authorize_browser_operation(
                    digest, project_id, datetime.now(UTC)
                )
                assert principal is not None

        async def update_membership(role: str):
            await service.execute(
                SetProjectMembershipCommand(second_admin_id, user_id, project_id, role)
            )

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
def test_revocation_during_authority_lock_wait_is_revalidated(postgres_engine, operation):
    _user_id, project_id, user_name = seed_user(postgres_engine)
    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    service = IdentityFixture(sessions, lambda: datetime.now(UTC))

    async def exercise():
        login = await perform_login(service, user_name, PASSWORD, project_id, ORIGIN)
        digest = service.digest(login.session_token)
        discovered, resume = asyncio.Event(), asyncio.Event()

        async def authorize():
            async with sessions() as session, session.begin():
                repository = SQLAlchemyIdentityRepository(session)
                original = repository._lock_user_projects

                async def paused_lookup(user_id, extra=()):
                    discovered.set()
                    await resume.wait()
                    return await original(user_id, extra)

                repository._lock_user_projects = paused_lookup
                if operation == "authorize":
                    return await repository.authorize_browser_operation(
                        digest, project_id, datetime.now(UTC)
                    )
                return await repository.select_project(
                    token_digest=digest, project_id=project_id, now=datetime.now(UTC)
                )

        pending = asyncio.create_task(authorize())
        await asyncio.wait_for(discovered.wait(), timeout=5)
        await service.execute(LogoutCommand(login.session_token, login.csrf_token, ORIGIN))
        resume.set()
        assert await asyncio.wait_for(pending, timeout=5) is None

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(database.dispose())

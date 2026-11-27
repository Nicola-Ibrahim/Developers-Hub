import asyncio
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from conftest import migration_config
from fastapi.testclient import TestClient
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from api.app import create_app
from api.core.errors import APIError
from backend import BackendContainer
from devops_platform.application.projects.register_project.command import RegisterProjectCommand
from devops_platform.infra.persistence.models.project_access import ProjectMembershipRow, ProjectRow
from devops_platform.infra.persistence.models.resources import Resource
from devops_platform.infra.persistence.repositories.project_access import (
    SQLAlchemyProjectAccessRules,
)
from devops_platform.infra.project_registration import RegisterProjectCommandHandler
from identity.application.api_tokens.create_personal_token.command import CreatePersonalTokenCommand
from identity.application.api_tokens.revoke_api_token.command import RevokeApiTokenCommand
from identity.application.api_tokens.revoke_api_token.handler import RevokeApiTokenHandler
from identity.application.interfaces.dispatch import IdentityModule
from identity.infra.persistence.models.api_token import ApiAccessTokenRow
from identity.infra.persistence.models.session import SessionRow
from identity.infra.persistence.models.user import InternalUserRow
from identity.infra.persistence.repositories.api_tokens import SQLAlchemyApiTokenRepository
from identity.infra.security.opaque_secrets import PepperedTokenHasher
from migrations.metadata import registered_metadata
from shared.authorization.credentials import RequestCredentials, SessionCredentials
from shared.infra.persistence.audit import AuditEvent
from shared.infra.persistence.unit_of_work import SqlAlchemyUnitOfWork
from shared.infra.settings import SCHEMA_REVISION, Settings

pytestmark = pytest.mark.postgres
PEPPER = "test-only-token-pepper-" * 3


def settings():
    return Settings(
        database_url="postgresql+psycopg://localhost/devops_hub_test", token_pepper=PEPPER
    )


def async_engine_for(sync_engine) -> AsyncEngine:
    """Use this fixture's unique schema and avoid pools crossing asyncio loops."""
    with sync_engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    assert isinstance(schema, str) and schema.startswith("test_")
    return create_async_engine(
        sync_engine.url,
        connect_args={"options": f"-csearch_path={schema}"},
        poolclass=NullPool,
        hide_parameters=True,
        echo=False,
    )


@contextmanager
def client_for(sync_engine, config=None):
    database = async_engine_for(sync_engine)
    try:
        with TestClient(create_app(config or settings(), engine=database)) as client:
            yield client
    finally:
        asyncio.run(database.dispose())


async def dispatch_browser(dispatch, credentials, session, message):
    credentials.identity = session
    return await dispatch(message)


async def issue_with_container(
    database: AsyncEngine, config, actor_id, project_id, session_token, csrf_token, **kwargs
):
    container = BackendContainer(config, engine=database).combined()
    try:
        async with container() as scope:
            module = await scope.get(IdentityModule)
            credentials = await scope.get(RequestCredentials)
            token, secret = await dispatch_browser(
                module.execute,
                credentials,
                SessionCredentials(session_token, csrf_token=csrf_token),
                CreatePersonalTokenCommand(
                    actor_id=actor_id,
                    project_id=project_id,
                    name="integration",
                    scopes=kwargs.get("scopes", ("catalog:read",)),
                    hours=kwargs.get("hours", 24),
                ),
            )
            return token.token_id, secret
    finally:
        await container.close()


async def register_project_with_container(database: AsyncEngine, config, project):
    container = BackendContainer(config, engine=database).combined()
    try:
        async with container() as scope:
            handler = await scope.get(RegisterProjectCommandHandler)
            return await handler.execute(
                RegisterProjectCommand(
                    name=project,
                    owning_team="test-team",
                    repository="example/repo",
                    environments=("dev",),
                )
            )
    finally:
        await container.close()


def register_project(sync_engine, project, config=None):
    database = async_engine_for(sync_engine)
    try:
        return asyncio.run(register_project_with_container(database, config or settings(), project))
    finally:
        asyncio.run(database.dispose())


def prepare_token_membership(sync_engine, user, project):
    session_token, csrf_token = f"session-{uuid4()}", f"csrf-{uuid4()}"
    hasher = PepperedTokenHasher(PEPPER)
    with Session(sync_engine) as session, session.begin():
        project_row = session.scalar(select(ProjectRow).where(ProjectRow.name == project))
        assert project_row is not None
        user_row = session.scalar(select(InternalUserRow).where(InternalUserRow.name == user))
        if user_row is None:
            user_row = InternalUserRow(name=user)
            session.add(user_row)
            session.flush()
        if session.get(ProjectMembershipRow, (user_row.id, project_row.id)) is None:
            session.add(
                ProjectMembershipRow(
                    user_id=user_row.id,
                    project_id=project_row.id,
                    role="developer",
                )
            )
        now = datetime.now(UTC)
        session.add(
            SessionRow(
                id=uuid4(),
                user_id=user_row.id,
                token_digest=hasher.digest(session_token),
                csrf_digest=hasher.digest(csrf_token),
                selected_project_id=project_row.id,
                credential_version=user_row.credential_version,
                created_at=now,
                last_seen_at=now,
                idle_expires_at=now + timedelta(hours=8),
                absolute_expires_at=now + timedelta(days=7),
            )
        )
        user_id, project_id = user_row.id, project_row.id
    return user_id, project_id, session_token, csrf_token


def issue(sync_engine, user="developer", project="project", **kwargs):
    database = async_engine_for(sync_engine)
    try:
        asyncio.run(register_project_with_container(database, settings(), project))
        credentials = prepare_token_membership(sync_engine, user, project)
        token_id, secret = asyncio.run(
            issue_with_container(database, settings(), *credentials, **kwargs)
        )
    finally:
        asyncio.run(database.dispose())
    return token_id, secret


async def revoke_with_container(database: AsyncEngine, token_id, config):
    container = BackendContainer(config, engine=database).combined()
    try:
        async with container() as scope:
            service = await scope.get(RevokeApiTokenHandler)
            return await service.execute(RevokeApiTokenCommand(token_id=token_id))
    finally:
        await container.close()


def revoke(sync_engine, token_id, config=None):
    database = async_engine_for(sync_engine)
    try:
        return asyncio.run(revoke_with_container(database, token_id, config or settings()))
    finally:
        asyncio.run(database.dispose())


def test_migrations_roundtrip_and_metadata_match(postgres_engine):
    with postgres_engine.begin() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == SCHEMA_REVISION
        assert compare_metadata(MigrationContext.configure(connection), registered_metadata()) == []
        command.downgrade(migration_config(connection), "base")
        assert set(inspect(connection).get_table_names()) == {"alembic_version"}
        command.upgrade(migration_config(connection), "head")
        assert compare_metadata(MigrationContext.configure(connection), registered_metadata()) == []


def test_issue_authenticate_and_revoke(postgres_engine, capsys):
    token_id, token = issue(postgres_engine)
    with Session(postgres_engine) as session:
        record = session.get(ApiAccessTokenRow, token_id)
        assert record.digest != token
        assert token not in record.digest
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1
    with client_for(postgres_engine) as client:
        assert client.get("/health/ready").status_code == 200
        headers = {"Authorization": "Bearer " + token}
        me = client.get("/api/v1/me", headers=headers)
        assert me.status_code == 200
        catalog = client.get("/api/v1/catalog", headers=headers)
        assert len(catalog.json()["templates"]) == 1
        assert catalog.json()["templates"][0]["requestable"] is False
        assert catalog.json()["templates"][0]["version"] == "16"
        assert token not in me.text + catalog.text
        assert revoke(postgres_engine, token_id)
        assert client.get("/api/v1/me", headers=headers).status_code == 401
    assert token not in capsys.readouterr().out


@pytest.mark.parametrize("change", ["expired", "disabled", "membership_removed", "wrong_token"])
def test_invalid_identity_and_membership_are_denied(postgres_engine, change):
    token_id, token = issue(postgres_engine)
    with Session(postgres_engine) as session, session.begin():
        record = session.get(ApiAccessTokenRow, token_id)
        if change == "expired":
            record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif change == "disabled":
            session.get(InternalUserRow, record.user_id).active = False
        elif change == "membership_removed":
            session.delete(session.get(ProjectMembershipRow, (record.user_id, record.project_id)))
        else:
            token = "wrong-" + token
    with client_for(postgres_engine) as client:
        assert (
            client.get("/api/v1/me", headers={"Authorization": "Bearer " + token}).status_code
            == 401
        )


def test_project_bound_principals_and_scope_enforcement(postgres_engine):
    _, first = issue(postgres_engine, user="one", project="one")
    _, second = issue(postgres_engine, user="two", project="two", scopes=("resources:read",))
    with client_for(postgres_engine) as client:
        one = client.get("/api/v1/me", headers={"Authorization": "Bearer " + first}).json()
        two = client.get("/api/v1/me", headers={"Authorization": "Bearer " + second}).json()
        assert one["project_id"] != two["project_id"]
        assert (
            client.get("/api/v1/catalog", headers={"Authorization": "Bearer " + second}).status_code
            == 403
        )


def test_failed_commit_rolls_back_new_token(postgres_engine):
    def fail_commit(session):
        raise RuntimeError("simulated commit failure")

    database = async_engine_for(postgres_engine)
    asyncio.run(register_project_with_container(database, settings(), "new"))
    credentials = prepare_token_membership(postgres_engine, "new", "new")
    event.listen(database.sync_engine, "commit", fail_commit)
    try:
        with pytest.raises(RuntimeError):
            asyncio.run(issue_with_container(database, settings(), *credentials))
    finally:
        event.remove(database.sync_engine, "commit", fail_commit)
        asyncio.run(database.dispose())
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(InternalUserRow)) == 1
        assert session.scalar(select(func.count()).select_from(ProjectMembershipRow)) == 1
        assert session.scalar(select(func.count()).select_from(ApiAccessTokenRow)) == 0
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_readiness_requires_expected_migration(postgres_engine):
    with postgres_engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'unexpected'"))
    with client_for(postgres_engine) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["code"] == "schema_not_ready"


def test_database_enforces_resource_state_and_lease(postgres_engine):
    token_id, _ = issue(postgres_engine)
    with Session(postgres_engine) as session:
        token = session.get(ApiAccessTokenRow, token_id)
        user_id, project_id = token.user_id, token.project_id
    with Session(postgres_engine) as session, pytest.raises(IntegrityError), session.begin():
        session.add(
            Resource(
                owner_id=user_id,
                project_id=project_id,
                display_name="db",
                template_id="postgres",
                target_id="local",
                size_id="small",
                configuration={},
                installation_id=uuid4(),
                status="invented",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )


def test_pre_refactor_token_digest_still_authenticates(postgres_engine):
    token_id, _ = issue(postgres_engine)
    # Captured from the old implementation using synthetic values before the move.
    legacy_token = "synthetic-existing-token-32-characters"
    legacy_pepper = "synthetic-fixed-pepper-32-characters"
    legacy_digest = "c61fc8cd60f22172e5a3dacc20bb3c56c23ce79b1b6cf8fc8f7f20a99e582d66"
    with Session(postgres_engine) as session, session.begin():
        session.get(ApiAccessTokenRow, token_id).digest = legacy_digest
    config = Settings(
        database_url="postgresql+psycopg://localhost/devops_hub_test", token_pepper=legacy_pepper
    )
    with client_for(postgres_engine, config) as client:
        assert (
            client.get(
                "/api/v1/me", headers={"Authorization": "Bearer " + legacy_token}
            ).status_code
            == 200
        )


def test_token_authentication_observes_role_committed_during_lock_wait(postgres_engine):
    user_id, project_id = uuid4(), uuid4()
    digest = PepperedTokenHasher(PEPPER).digest("synthetic-token-for-membership-lock-test")
    with Session(postgres_engine) as session, session.begin():
        session.add_all(
            [
                InternalUserRow(id=user_id, name=f"user-{user_id}", active=True),
                ProjectRow(id=project_id, name=f"project-{project_id}"),
            ]
        )
        session.flush()
        session.add_all(
            [
                ProjectMembershipRow(user_id=user_id, project_id=project_id, role="admin"),
                ApiAccessTokenRow(
                    user_id=user_id,
                    project_id=project_id,
                    digest=digest,
                    scopes=["resources:read"],
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                ),
            ]
        )

    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database)

    async def exercise():
        lookup_started = asyncio.Event()
        lookup_pid = None

        async def authenticate():
            nonlocal lookup_pid
            async with sessions.begin() as session:
                lookup_pid = await session.scalar(text("SELECT pg_backend_pid()"))
                lookup_started.set()
                repository = SQLAlchemyApiTokenRepository(
                    session, SQLAlchemyProjectAccessRules(session)
                )
                return await repository.find_token_credential(digest)

        lookup = None
        try:
            async with asyncio.timeout(10):
                async with sessions.begin() as writer:
                    writer_pid = await writer.scalar(text("SELECT pg_backend_pid()"))
                    membership = await writer.get(ProjectMembershipRow, (user_id, project_id))
                    assert membership is not None
                    membership.role = "developer"
                    await writer.flush()
                    lookup = asyncio.create_task(authenticate())
                    await lookup_started.wait()
                    while True:
                        blockers = await writer.scalar(
                            text("SELECT pg_blocking_pids(:pid)"), {"pid": lookup_pid}
                        )
                        if writer_pid in blockers:
                            break
                        if lookup.done():
                            pytest.fail(
                                f"Token lookup did not wait for membership: {lookup.result()!r}"
                            )
                        await asyncio.sleep(0.01)
                return await lookup
        finally:
            if lookup is not None and not lookup.done():
                lookup.cancel()
                await asyncio.gather(lookup, return_exceptions=True)
            await database.dispose()

    snapshot = asyncio.run(exercise())
    assert snapshot is not None
    assert snapshot.role == "developer"


def test_disabled_account_cannot_receive_token_for_current_membership(postgres_engine):
    token_id, _ = issue(postgres_engine)
    from devops_platform.infra.persistence.models.project_access import ProjectRow

    with Session(postgres_engine) as session, session.begin():
        session.get(
            InternalUserRow, session.get(ApiAccessTokenRow, token_id).user_id
        ).active = False
    register_project(postgres_engine, "second")
    with pytest.raises(APIError) as rejected:
        issue(postgres_engine, project="second")
    assert rejected.value.status == 401
    with Session(postgres_engine) as session:
        # Project registration is already committed independently of identity token issuance.
        assert session.scalar(select(func.count()).select_from(ProjectRow)) == 2
        assert session.scalar(select(func.count()).select_from(ProjectMembershipRow)) == 2
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


@pytest.mark.parametrize("account_exists", [False, True])
def test_token_issuance_does_not_create_missing_account_or_membership(
    postgres_engine, account_exists
):
    project_id = register_project(postgres_engine, "existing-project").project_id
    user_id = uuid4()
    session_token, csrf_token = f"session-{uuid4()}", f"csrf-{uuid4()}"
    hasher = PepperedTokenHasher(PEPPER)
    if account_exists:
        with Session(postgres_engine) as session, session.begin():
            user = InternalUserRow(id=user_id, name="unprovisioned")
            session.add(user)
            session.flush()
            now = datetime.now(UTC)
            session.add(
                SessionRow(
                    id=uuid4(),
                    user_id=user.id,
                    token_digest=hasher.digest(session_token),
                    csrf_digest=hasher.digest(csrf_token),
                    selected_project_id=project_id,
                    credential_version=user.credential_version,
                    created_at=now,
                    last_seen_at=now,
                    idle_expires_at=now + timedelta(hours=8),
                    absolute_expires_at=now + timedelta(days=7),
                )
            )
    database = async_engine_for(postgres_engine)
    try:
        with pytest.raises(APIError) as rejected:
            asyncio.run(
                issue_with_container(
                    database, settings(), user_id, project_id, session_token, csrf_token
                )
            )
        assert rejected.value.status == 401
    finally:
        asyncio.run(database.dispose())
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(InternalUserRow)) == int(
            account_exists
        )
        assert session.scalar(select(func.count()).select_from(ProjectMembershipRow)) == 0
        assert session.scalar(select(func.count()).select_from(ApiAccessTokenRow)) == 0
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_revoke_is_idempotent_and_does_not_duplicate_audit(postgres_engine):
    token_id, _ = issue(postgres_engine)
    assert revoke(postgres_engine, token_id)
    assert revoke(postgres_engine, token_id)
    assert not revoke(postgres_engine, uuid4())
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 2


def test_concurrent_token_revocation_preserves_first_timestamp_and_single_audit(postgres_engine):
    token_id, _ = issue(postgres_engine)
    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    first_revocation_times = []
    first_token_locked = asyncio.Event()
    second_query_started = asyncio.Event()
    release_first = asyncio.Event()
    backend_pids = {}

    class PausingTransaction:
        async def run(self, action):
            async with sessions() as session:
                unit = SqlAlchemyUnitOfWork(session)
                repository = SQLAlchemyApiTokenRepository(
                    session, SQLAlchemyProjectAccessRules(session)
                )

                class PausingRepository:
                    async def find_api_token(self, token_id):
                        status = await repository.find_api_token(token_id)
                        backend_pids["first"] = await session.scalar(
                            text("SELECT pg_backend_pid()")
                        )
                        first_token_locked.set()
                        await release_first.wait()
                        return status

                    async def revoke_api_token(self, token_id, revoked_at):
                        first_revocation_times.append(revoked_at)
                        await repository.revoke_api_token(token_id, revoked_at)

                    async def record_token_audit(self, event):
                        await repository.record_token_audit(event)

                return await unit.run(lambda: action(PausingRepository()), lambda result: result)

    class ObservedTransaction:
        async def run(self, action):
            async with sessions() as session:
                unit = SqlAlchemyUnitOfWork(session)
                repository = SQLAlchemyApiTokenRepository(
                    session, SQLAlchemyProjectAccessRules(session)
                )

                async def run_action():
                    backend_pids["second"] = await session.scalar(text("SELECT pg_backend_pid()"))
                    second_query_started.set()
                    return await action(repository)

                return await unit.run(run_action, lambda result: result)

    async def wait_until_second_is_blocked():
        await asyncio.wait_for(second_query_started.wait(), timeout=10)
        for _ in range(500):
            async with sessions() as observer:
                result = await observer.execute(
                    text("SELECT pg_blocking_pids(:backend_pid)"),
                    {"backend_pid": backend_pids["second"]},
                )
                blockers = result.scalar_one()
            if backend_pids["first"] in blockers:
                return
            await asyncio.sleep(0.01)
        raise AssertionError("second revocation did not block on the first token lock")

    async def exercise():
        tasks = []
        try:
            first_handler = RevokeApiTokenHandler(PausingTransaction())
            first_task = asyncio.create_task(
                first_handler.execute(RevokeApiTokenCommand(token_id=token_id))
            )
            tasks.append(first_task)
            await asyncio.wait_for(first_token_locked.wait(), timeout=10)
            second_handler = RevokeApiTokenHandler(ObservedTransaction())
            second_task = asyncio.create_task(
                second_handler.execute(RevokeApiTokenCommand(token_id=token_id))
            )
            tasks.append(second_task)
            await wait_until_second_is_blocked()
            release_first.set()
            return await asyncio.wait_for(asyncio.gather(first_task, second_task), timeout=10)
        finally:
            release_first.set()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await database.dispose()

    assert asyncio.run(exercise()) == [True, True]
    with Session(postgres_engine) as session:
        token = session.get(ApiAccessTokenRow, token_id)
        assert first_revocation_times == [token.revoked_at]
        persisted_revocation = token.revoked_at
        revocation_audits = session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "token_revoked",
                AuditEvent.request_id == token_id,
            )
        ).all()
        assert len(revocation_audits) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 2

    assert revoke(postgres_engine, token_id)
    with Session(postgres_engine) as session:
        assert session.get(ApiAccessTokenRow, token_id).revoked_at == persisted_revocation
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.action == "token_revoked",
                    AuditEvent.request_id == token_id,
                )
            )
            == 1
        )

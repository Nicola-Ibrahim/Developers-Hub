import asyncio
import stat
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
from composition.container import BackendContainer
from composition.integrations.project_registration import RegisterProjectCommandHandler
from devops_platform.application.projects.command import RegisterProjectCommand
from devops_platform.infra.persistence.models.project_access import ProjectMembershipRow, ProjectRow
from devops_platform.infra.persistence.models.resources import Resource
from identity.application.api_tokens.issue_api_token.command import IssueApiTokenCommand
from identity.application.api_tokens.revoke_api_token.command import RevokeApiTokenCommand
from identity.application.api_tokens.revoke_api_token.handler import RevokeApiTokenHandler
from identity.application.shared.errors import CredentialDeliveryError
from identity.infra.composition.api_token_transactions import IssueApiTokenToFile
from identity.infra.persistence.models.api_token import ApiAccessTokenRow
from identity.infra.persistence.models.user import InternalUserRow
from identity.infra.persistence.repositories.api_tokens import SQLAlchemyApiTokenRepository
from identity.infra.security.credential_file import PrivateCredentialFile
from migrations.metadata import registered_metadata
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


async def issue_with_container(database: AsyncEngine, path, config, user, project, **kwargs):
    container = BackendContainer(config, engine=database).combined()
    try:
        async with container() as scope:
            service = await scope.get(IssueApiTokenToFile)
            return await service.execute(
                IssueApiTokenCommand(user_name=user, project_name=project, **kwargs),
                PrivateCredentialFile(path),
            )
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


def issue(sync_engine, path, user="developer", project="project", **kwargs):
    database = async_engine_for(sync_engine)
    try:
        asyncio.run(register_project_with_container(database, settings(), project))
        token_id = asyncio.run(
            issue_with_container(database, path, settings(), user, project, **kwargs)
        )
    finally:
        asyncio.run(database.dispose())
    return token_id, path.read_text().strip()


async def revoke_with_container(database: AsyncEngine, token_id, config):
    container = BackendContainer(config, engine=database).combined()
    try:
        async with container() as scope:
            service = await scope.get(RevokeApiTokenHandler)
            return await service.execute(RevokeApiTokenCommand(token_id))
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


def test_issue_authenticate_and_revoke(postgres_engine, tmp_path, capsys):
    token_id, token = issue(postgres_engine, tmp_path / "credential")
    assert stat.S_IMODE((tmp_path / "credential").stat().st_mode) == 0o600
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
def test_invalid_identity_and_membership_are_denied(postgres_engine, tmp_path, change):
    token_id, token = issue(postgres_engine, tmp_path / "credential")
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


def test_project_bound_principals_and_scope_enforcement(postgres_engine, tmp_path):
    _, first = issue(postgres_engine, tmp_path / "one", user="one", project="one")
    _, second = issue(
        postgres_engine, tmp_path / "two", user="two", project="two", scopes=("resources:read",)
    )
    with client_for(postgres_engine) as client:
        one = client.get("/api/v1/me", headers={"Authorization": "Bearer " + first}).json()
        two = client.get("/api/v1/me", headers={"Authorization": "Bearer " + second}).json()
        assert one["project_id"] != two["project_id"]
        assert (
            client.get("/api/v1/catalog", headers={"Authorization": "Bearer " + second}).status_code
            == 403
        )


def test_existing_output_does_not_get_overwritten_or_commit_identity(postgres_engine, tmp_path):
    output = tmp_path / "existing"
    output.write_text("original")
    with pytest.raises(CredentialDeliveryError):
        issue(postgres_engine, output, user="new", project="new")
    assert output.read_text() == "original"
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(InternalUserRow)) == 0
        assert session.scalar(select(func.count()).select_from(ApiAccessTokenRow)) == 0
        assert session.scalar(select(func.count()).select_from(ProjectMembershipRow)) == 0
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0
        # Trusted project registration is a separate, prior operator operation.
        assert session.scalar(select(func.count()).select_from(ProjectRow)) == 1


def test_failed_commit_removes_new_token_file(postgres_engine, tmp_path):
    def fail_commit(session):
        raise RuntimeError("simulated commit failure")

    output = tmp_path / "credential"
    database = async_engine_for(postgres_engine)
    asyncio.run(register_project_with_container(database, settings(), "new"))
    event.listen(database.sync_engine, "commit", fail_commit)
    try:
        with pytest.raises(RuntimeError):
            asyncio.run(issue_with_container(database, output, settings(), "new", "new"))
    finally:
        event.remove(database.sync_engine, "commit", fail_commit)
        asyncio.run(database.dispose())
    assert not output.exists()
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(ApiAccessTokenRow)) == 0


def test_readiness_requires_expected_migration(postgres_engine):
    with postgres_engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'unexpected'"))
    with client_for(postgres_engine) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["code"] == "schema_not_ready"


def test_database_enforces_resource_state_and_lease(postgres_engine, tmp_path):
    token_id, _ = issue(postgres_engine, tmp_path / "credential")
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


def test_pre_refactor_token_digest_still_authenticates(postgres_engine, tmp_path):
    token_id, _ = issue(postgres_engine, tmp_path / "credential")
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


def test_disabled_issuance_rolls_back_membership_for_registered_project(postgres_engine, tmp_path):
    token_id, _ = issue(postgres_engine, tmp_path / "credential")
    from devops_platform.infra.persistence.models.project_access import ProjectRow
    from identity.domain.errors import IdentityValidationError

    with Session(postgres_engine) as session, session.begin():
        session.get(
            InternalUserRow, session.get(ApiAccessTokenRow, token_id).user_id
        ).active = False
    register_project(postgres_engine, "second")
    with pytest.raises(IdentityValidationError):
        issue(postgres_engine, tmp_path / "second", project="second")
    with Session(postgres_engine) as session:
        # Project registration is already committed independently of identity token issuance.
        assert session.scalar(select(func.count()).select_from(ProjectRow)) == 2
        assert session.scalar(select(func.count()).select_from(ProjectMembershipRow)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1
    assert not (tmp_path / "second").exists()


def test_revoke_is_idempotent_and_does_not_duplicate_audit(postgres_engine, tmp_path):
    token_id, _ = issue(postgres_engine, tmp_path / "credential")
    assert revoke(postgres_engine, token_id)
    assert revoke(postgres_engine, token_id)
    assert not revoke(postgres_engine, uuid4())
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 2


def test_concurrent_token_revocation_preserves_first_timestamp_and_single_audit(
    postgres_engine, tmp_path
):
    token_id, _ = issue(postgres_engine, tmp_path / "credential")
    database = async_engine_for(postgres_engine)
    sessions = async_sessionmaker(database, expire_on_commit=False)
    first_revoked_at = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    second_revoked_at = datetime(2026, 11, 19, 12, 1, tzinfo=UTC)
    first_token_locked = asyncio.Event()
    second_query_started = asyncio.Event()
    release_first = asyncio.Event()
    backend_pids = {}

    class PausingTransaction:
        async def run(self, action):
            async with sessions() as session:
                unit = SqlAlchemyUnitOfWork(session)
                repository = SQLAlchemyApiTokenRepository(session)

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
                        await repository.revoke_api_token(token_id, revoked_at)

                    async def record_token_audit(self, event):
                        await repository.record_token_audit(event)

                return await unit.run(lambda: action(PausingRepository()), lambda result: result)

    class ObservedTransaction:
        async def run(self, action):
            async with sessions() as session:
                unit = SqlAlchemyUnitOfWork(session)
                repository = SQLAlchemyApiTokenRepository(session)

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
            first_handler = RevokeApiTokenHandler(PausingTransaction(), lambda: first_revoked_at)
            first_task = asyncio.create_task(first_handler.execute(RevokeApiTokenCommand(token_id)))
            tasks.append(first_task)
            await asyncio.wait_for(first_token_locked.wait(), timeout=10)
            second_handler = RevokeApiTokenHandler(ObservedTransaction(), lambda: second_revoked_at)
            second_task = asyncio.create_task(
                second_handler.execute(RevokeApiTokenCommand(token_id))
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
        assert token.revoked_at == first_revoked_at
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

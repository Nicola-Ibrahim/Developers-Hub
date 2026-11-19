"""Application resources use the same current-authority, quota and replay ledger."""

import asyncio
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import event, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import Session
from test_foundation_postgres import async_engine_for, client_for, issue

from composition.integrations.application_resources import LedgerApplicationResources
from devops_platform.application.interfaces.software_delivery import (
    ApplicationDeliveryFailure,
)
from devops_platform.application.resource_management.catalog.catalog import ApprovedPostgresCatalog
from devops_platform.application.resource_management.catalog.models import PostgresOption
from devops_platform.application.software_delivery.attach_database.command import (
    ResourceAttachmentSpec,
)
from devops_platform.infra.composition.application_bindings import (
    SQLAlchemyApplicationDatabaseBindings,
)
from devops_platform.infra.persistence.models.delivery import ApplicationRow
from devops_platform.infra.persistence.models.project_access import ProjectMembershipRow
from devops_platform.infra.persistence.models.resources import (
    QuotaBudget,
    Reservation,
    Resource,
    ResourceSecret,
)
from devops_platform.infra.providers.application_runtime import (
    managed_resource_container_name,
)
from devops_platform.infra.security.credentials import FernetResourceCredentialCipher

pytestmark = pytest.mark.postgres


async def _wait_until_binding_is_lock_blocked(database: AsyncEngine, application_name: str) -> None:
    async with database.connect() as connection:
        for _ in range(250):
            waiting = await connection.scalar(
                text(
                    """SELECT EXISTS (
                           SELECT 1 FROM pg_stat_activity
                           WHERE application_name = :application_name
                             AND state = 'active'
                             AND wait_event_type = 'Lock'
                       )"""
                ),
                {"application_name": application_name},
            )
            if waiting:
                return
            await asyncio.sleep(0.02)
    raise AssertionError("binding resolver never waited on the held application row lock")


def test_binding_samples_resource_lease_after_application_lock(postgres_engine, tmp_path):
    _, token = issue(
        postgres_engine,
        tmp_path / "binding-lease-credential",
        project=f"binding-lease-{uuid4().hex}",
    )
    with client_for(postgres_engine) as client:
        project = client.get(
            "/api/v1/projects", headers={"Authorization": "Bearer " + token}
        ).json()[0]
    project_id = UUID(project["project_id"])
    environment_id = UUID(project["environments"][0]["id"])
    with Session(postgres_engine) as session:
        owner_id = session.scalar(
            select(ProjectMembershipRow.user_id).where(
                ProjectMembershipRow.project_id == project_id
            )
        )
    assert owner_id is not None

    installation_id, application_id, resource_id = uuid4(), uuid4(), uuid4()
    cipher = FernetResourceCredentialCipher(Fernet.generate_key().decode(), "test-key")
    resource_name = managed_resource_container_name(installation_id, resource_id)
    application_name = f"binding-lease-{uuid4().hex}"
    database = async_engine_for(postgres_engine)

    @event.listens_for(database.sync_engine, "connect")
    def set_test_application_name(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("SELECT set_config('application_name', %s, false)", (application_name,))
        cursor.close()

    sessions = async_sessionmaker(database, expire_on_commit=False)
    adapter = SQLAlchemyApplicationDatabaseBindings(sessions, installation_id, cipher)
    with Session(postgres_engine) as session, session.begin():
        created_at = session.scalar(select(func.clock_timestamp()))
        assert isinstance(created_at, datetime)
        session.add(
            Resource(
                id=resource_id,
                environment_id=environment_id,
                owner_id=owner_id,
                project_id=project_id,
                display_name="lease-regression-db",
                template_id="postgres",
                target_id="local",
                size_id="small",
                configuration={},
                work_reference=None,
                desired_state="running",
                status="ready",
                revision=1,
                generation=1,
                installation_id=installation_id,
                provider_id=resource_name,
                endpoint={"host": "127.0.0.1", "port": 5432},
                created_at=created_at,
                expires_at=created_at + timedelta(minutes=1),
            )
        )
        session.flush()
        session.add(
            ResourceSecret(
                resource_id=resource_id,
                key_id=cipher.key_id,
                ciphertext=b"unused-after-expiry-check",
            )
        )
        session.add(
            ApplicationRow(
                id=application_id,
                project_id=project_id,
                environment_id=environment_id,
                owner_id=owner_id,
                name="lease-regression-app",
                template_id="fastapi",
                template_version="1",
                resource_id=resource_id,
                status="ready",
            )
        )

    async def exercise():
        resolver = None
        try:
            async with sessions() as lock_session, lock_session.begin():
                await lock_session.scalar(
                    select(ApplicationRow)
                    .where(ApplicationRow.id == application_id)
                    .with_for_update()
                )
                resolver = asyncio.create_task(
                    adapter.resolve(project_id, application_id, resource_id)
                )
                await _wait_until_binding_is_lock_blocked(database, application_name)
                # The resolver has not passed its application lock yet. Expiring
                # the lease now makes any timestamp sampled before that wait stale.
                await lock_session.execute(
                    update(Resource)
                    .where(Resource.id == resource_id)
                    .values(expires_at=func.clock_timestamp())
                )

            with pytest.raises(ApplicationDeliveryFailure) as failure:
                await asyncio.wait_for(resolver, timeout=5)
            assert failure.value.code == "resource_not_ready"
        finally:
            if resolver is not None and not resolver.done():
                resolver.cancel()
                await asyncio.gather(resolver, return_exceptions=True)

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(database.dispose())


def test_attachment_replays_and_cleanup_keeps_reservation_until_worker_confirms(
    postgres_engine, tmp_path
):
    _, token = issue(postgres_engine, tmp_path / "credential")
    with client_for(postgres_engine) as client:
        project = client.get(
            "/api/v1/projects", headers={"Authorization": "Bearer " + token}
        ).json()[0]
    project_id, environment = UUID(project["project_id"]), UUID(project["environments"][0]["id"])
    with Session(postgres_engine) as session, session.begin():
        owner = session.scalar(
            select(ProjectMembershipRow.user_id).where(
                ProjectMembershipRow.project_id == project_id
            )
        )
        session.add(
            QuotaBudget(
                scope="target",
                scope_id="local",
                max_resources=2,
                max_cpu_millis=2000,
                max_memory_bytes=2**31,
                max_storage_bytes=2**32,
            )
        )
    database = async_engine_for(postgres_engine)
    adapter = LedgerApplicationResources(
        async_sessionmaker(database, expire_on_commit=False),
        ApprovedPostgresCatalog((PostgresOption(requestable=True, unavailable_reason=None),)),
        uuid4(),
    )

    async def exercise():
        kwargs = dict(
            project_id=project_id,
            environment_id=environment,
            owner_id=owner,
            command=ResourceAttachmentSpec("postgres", "16", "local", "small", 3600),
            idempotency_key="application:resource:stable-key",
        )
        first = await adapter.request(**kwargs)
        assert await adapter.request(**kwargs) == first
        assert not await adapter.ready(project_id, first)
        with pytest.raises(ApplicationDeliveryFailure, match="resource_cleanup_pending"):
            await adapter.delete(project_id, owner, first, "cleanup")
        with Session(postgres_engine) as session:
            assert session.scalar(select(func.count()).select_from(Resource)) == 1
            assert session.get(Resource, first).desired_state == "deleted"
            assert session.get(Reservation, first).released_at is None
        with Session(postgres_engine) as session, session.begin():
            session.delete(session.get(ProjectMembershipRow, (owner, project_id)))
        with pytest.raises(ApplicationDeliveryFailure, match="resource_owner_not_authorized"):
            await adapter.request(**kwargs)

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(database.dispose())

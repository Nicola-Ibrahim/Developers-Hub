"""PostgreSQL checks for canonical webhook repository lookup and preview targets."""

import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Session
from test_foundation_postgres import async_engine_for

from devops_platform.application.software_delivery.handle_preview_webhook.command import (
    ProcessGithubPreviewWebhook,
)
from devops_platform.application.software_delivery.handle_preview_webhook.handler import (
    ProcessGithubPreviewWebhookHandler,
)
from devops_platform.infra.persistence.models.delivery import (
    ApplicationDeliveryStepRow,
    ApplicationRow,
)
from devops_platform.infra.persistence.models.project import (
    ProjectEnvironmentRow,
    ProjectRegistrationRow,
)
from devops_platform.infra.persistence.models.project_access import ProjectRow, TeamRow
from devops_platform.infra.persistence.repositories.delivery import (
    SQLAlchemyApplicationDeliveryRepository,
)
from devops_platform.infra.security.webhooks import HmacGitHubWebhookVerifier
from identity.infra.persistence.models.user import InternalUserRow

pytestmark = pytest.mark.postgres
_WEBHOOK_SECRET = "preview-webhook-postgres-test-secret"


def _register(
    session: Session,
    *,
    repository: str,
    environments: tuple[str, ...],
) -> tuple[UUID, UUID, dict[str, UUID]]:
    project_id, team_id, user_id = uuid4(), uuid4(), uuid4()
    project_name = f"webhook-{project_id}"
    session.add_all(
        [
            ProjectRow(id=project_id, name=project_name),
            TeamRow(id=team_id, name=f"webhook-team-{team_id}"),
            InternalUserRow(id=user_id, name=f"webhook-user-{user_id}"),
        ]
    )
    session.flush()
    session.add(
        ProjectRegistrationRow(
            project_id=project_id,
            name=project_name,
            owning_team_id=team_id,
            owning_team_name="webhook-test",
            repository=repository,
            configured=True,
        )
    )
    session.flush()
    environment_ids = {}
    for environment in environments:
        environment_id = uuid4()
        environment_ids[environment] = environment_id
        session.add(
            ProjectEnvironmentRow(
                id=environment_id,
                project_id=project_id,
                name=environment,
            )
        )
    session.flush()
    return project_id, user_id, environment_ids


def _create_preview(
    postgres_engine,
    *,
    project_id: UUID,
    owner_id: UUID,
    repository_name: str,
    pull_request: int,
    now: datetime,
) -> UUID:
    async def exercise() -> UUID:
        engine = async_engine_for(postgres_engine)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as session, session.begin():
                repository = SQLAlchemyApplicationDeliveryRepository(session)
                application_id = await repository.request_preview(
                    project_id=project_id,
                    owner_id=owner_id,
                    repository=repository_name,
                    pull_request=pull_request,
                    branch="feature-preview",
                    head_sha="c" * 40,
                    image_digest=None,
                    template_id="python-fastapi",
                    template_version="1.0.0",
                    ttl_seconds=600,
                    now=now,
                )
                assert application_id is not None
                return application_id
        finally:
            await engine.dispose()

    return asyncio.run(exercise())


def _signed_close(
    repository_name: str, delivery_id: str, now: datetime
) -> ProcessGithubPreviewWebhook:
    body = json.dumps(
        {
            "action": "closed",
            "repository": {"full_name": repository_name},
            "pull_request": {"number": 41},
        },
        separators=(",", ":"),
    ).encode()
    digest = hmac.new(_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return ProcessGithubPreviewWebhook(
        raw_body=body,
        signature=f"sha256={digest}",
        delivery_id=delivery_id,
        event="pull_request",
        now=now,
    )


def _handle_signed_close(postgres_engine, command: ProcessGithubPreviewWebhook):
    async def exercise():
        engine = async_engine_for(postgres_engine)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as session, session.begin():
                repository = SQLAlchemyApplicationDeliveryRepository(session)
                handler = ProcessGithubPreviewWebhookHandler(
                    repository=repository,
                    images=None,
                    webhook_verifier=HmacGitHubWebhookVerifier(_WEBHOOK_SECRET),
                    allowed_repository_owner="company",
                    preview_owner_id=uuid4(),
                    preview_ttl_seconds=600,
                )
                return await handler.execute(command)
        finally:
            await engine.dispose()

    return asyncio.run(exercise())


def test_registered_repository_uses_literal_canonical_equality(postgres_engine) -> None:
    with Session(postgres_engine) as session, session.begin():
        _register(session, repository="company/axb", environments=("preview",))

    async def exercise() -> None:
        engine = async_engine_for(postgres_engine)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as session:
                repository = SQLAlchemyApplicationDeliveryRepository(session)
                assert await repository.find_registered_repository("company/a_b") is None
                registered = await repository.find_registered_repository("COMPANY/AXB")
                assert registered is not None
                assert registered.canonical_repository == "company/axb"
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_registered_repository_fails_closed_on_canonical_duplicates(postgres_engine) -> None:
    with Session(postgres_engine) as session, session.begin():
        _register(session, repository="company/example", environments=("preview",))
        _register(session, repository="COMPANY/EXAMPLE", environments=("preview",))

    async def exercise() -> None:
        engine = async_engine_for(postgres_engine)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as session:
                repository = SQLAlchemyApplicationDeliveryRepository(session)
                assert await repository.find_registered_repository("company/example") is None
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_preview_creation_requires_named_preview_environment(postgres_engine) -> None:
    with Session(postgres_engine) as session, session.begin():
        project_id, owner_id, environments = _register(
            session,
            repository="company/preview-target",
            environments=("dev", "preview", "staging"),
        )
        preview_environment_id = environments["preview"]

    async def exercise() -> None:
        engine = async_engine_for(postgres_engine)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        now = datetime.now(UTC)
        try:
            async with sessions() as session, session.begin():
                repository = SQLAlchemyApplicationDeliveryRepository(session)
                registered = await repository.find_registered_repository("company/preview-target")
                assert registered is not None
                assert registered.environment_id == preview_environment_id
                application_id = await repository.request_preview(
                    project_id=project_id,
                    owner_id=owner_id,
                    repository="company/preview-target",
                    pull_request=31,
                    branch="feature-preview",
                    head_sha="a" * 40,
                    image_digest=None,
                    template_id="python-fastapi",
                    template_version="1.0.0",
                    ttl_seconds=600,
                    now=now,
                )
                assert application_id is not None
            async with sessions() as session:
                application = await session.get(ApplicationRow, application_id)
                assert application is not None
                assert application.environment_id == preview_environment_id
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_preview_creation_does_not_fall_back_without_preview_environment(postgres_engine) -> None:
    with Session(postgres_engine) as session, session.begin():
        project_id, owner_id, _ = _register(
            session,
            repository="company/no-preview",
            environments=("dev", "staging"),
        )

    async def exercise() -> None:
        engine = async_engine_for(postgres_engine)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as session, session.begin():
                repository = SQLAlchemyApplicationDeliveryRepository(session)
                assert await repository.find_registered_repository("company/no-preview") is None
                assert (
                    await repository.request_preview(
                        project_id=project_id,
                        owner_id=owner_id,
                        repository="company/no-preview",
                        pull_request=32,
                        branch="feature-preview",
                        head_sha="b" * 40,
                        image_digest=None,
                        template_id="python-fastapi",
                        template_version="1.0.0",
                        ttl_seconds=600,
                        now=datetime.now(UTC),
                    )
                    is None
                )
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_signed_close_cleans_up_with_ambiguous_mapping_and_replays_once(postgres_engine) -> None:
    now = datetime.now(UTC)
    with Session(postgres_engine) as session, session.begin():
        project_id, owner_id, _ = _register(
            session,
            repository="company/close-ambiguous",
            environments=("preview",),
        )
    application_id = _create_preview(
        postgres_engine,
        project_id=project_id,
        owner_id=owner_id,
        repository_name="company/close-ambiguous",
        pull_request=41,
        now=now,
    )
    with Session(postgres_engine) as session, session.begin():
        _register(
            session,
            repository="COMPANY/CLOSE-AMBIGUOUS",
            environments=("preview",),
        )

    delivery_id = uuid4().hex
    first = _handle_signed_close(
        postgres_engine, _signed_close("company/close-ambiguous", delivery_id, now)
    )
    replay = _handle_signed_close(
        postgres_engine, _signed_close("company/close-ambiguous", delivery_id, now)
    )

    assert first.accepted and not first.duplicate and first.cleanup_count == 1
    assert replay.accepted and replay.duplicate and replay.reason == "duplicate_delivery"
    with Session(postgres_engine) as session:
        application = session.get(ApplicationRow, application_id)
        assert application is not None and application.status == "deleting"
        assert (
            session.scalar(
                select(func.count())
                .select_from(ApplicationDeliveryStepRow)
                .where(
                    ApplicationDeliveryStepRow.application_id == application_id,
                    ApplicationDeliveryStepRow.kind == "preview_cleanup",
                )
            )
            == 1
        )


def test_signed_close_cleans_up_when_registration_mapping_is_missing(postgres_engine) -> None:
    now = datetime.now(UTC)
    with Session(postgres_engine) as session, session.begin():
        project_id, owner_id, _ = _register(
            session,
            repository="company/close-unregistered",
            environments=("preview",),
        )
    application_id = _create_preview(
        postgres_engine,
        project_id=project_id,
        owner_id=owner_id,
        repository_name="company/close-unregistered",
        pull_request=41,
        now=now,
    )
    with Session(postgres_engine) as session, session.begin():
        registration = session.get(ProjectRegistrationRow, project_id)
        assert registration is not None
        registration.configured = False

    result = _handle_signed_close(
        postgres_engine,
        _signed_close("company/close-unregistered", uuid4().hex, now),
    )

    assert result.accepted and not result.duplicate and result.cleanup_count == 1
    with Session(postgres_engine) as session:
        application = session.get(ApplicationRow, application_id)
        assert application is not None and application.status == "deleting"


def test_signed_close_for_mismatched_repository_leaves_preview_alone(postgres_engine) -> None:
    now = datetime.now(UTC)
    with Session(postgres_engine) as session, session.begin():
        project_id, owner_id, _ = _register(
            session,
            repository="company/close-exact",
            environments=("preview",),
        )
    application_id = _create_preview(
        postgres_engine,
        project_id=project_id,
        owner_id=owner_id,
        repository_name="company/close-exact",
        pull_request=41,
        now=now,
    )

    result = _handle_signed_close(
        postgres_engine,
        _signed_close("company/close-other", uuid4().hex, now),
    )

    assert result.accepted and not result.duplicate and result.cleanup_count == 0
    with Session(postgres_engine) as session:
        application = session.get(ApplicationRow, application_id)
        assert application is not None and application.status == "pending"
        assert (
            session.scalar(
                select(func.count())
                .select_from(ApplicationDeliveryStepRow)
                .where(
                    ApplicationDeliveryStepRow.application_id == application_id,
                    ApplicationDeliveryStepRow.kind == "preview_cleanup",
                )
            )
            == 0
        )

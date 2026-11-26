"""The HTTP platform host owns one Dishka ACTION scope per dispatch."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from dishka import AsyncContainer, Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend import BackendContainer
from devops_platform.application.interfaces.module import DeveloperPlatformModule
from devops_platform.application.interfaces.resources import ResourceRepository
from devops_platform.application.resource_management.get_resource.query import ReadResource
from devops_platform.application.resource_management.read_models import ResourceDetails
from devops_platform.application.shared.dto import AccessContext
from shared.authorization.interfaces import AuthorizationDecisionPort
from shared.authorization.models import AuthorizationDecision
from shared.infra.settings import Settings


class _Session:
    def __init__(self) -> None:
        self.begins = 0
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    async def begin(self) -> None:
        self.begins += 1

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def close(self) -> None:
        self.closes += 1

    async def scalar(self, _statement):
        return None


class _Authorizer:
    async def evaluate(self, _request):
        return AuthorizationDecision(True)


class _AuthorizerOverride(Provider):
    authorizer = provide(
        _Authorizer,
        provides=AuthorizationDecisionPort,
        scope=Scope.APP,
        override=True,
    )


class _ResourceReads:
    def __init__(self, tracker: _ResourceReadTracker) -> None:
        self.tracker = tracker
        self.session: AsyncSession | None = None
        tracker.repositories.append(self)

    async def find_resource(self, project_id, resource_id) -> ResourceDetails:
        assert self.session is not None
        self.tracker.sessions_used.append(self.session)
        now = datetime.now(UTC)
        return ResourceDetails(
            id=resource_id,
            project_id=project_id,
            environment_id=None,
            owner_id=uuid4(),
            display_name="test-resource",
            template_id="postgres",
            target_id="local",
            size_id="small",
            desired_state="running",
            status="ready",
            revision=1,
            created_at=now,
            expires_at=now,
            failure_code=None,
        )


class _ResourceReadTracker:
    def __init__(self) -> None:
        self.repositories: list[_ResourceReads] = []
        self.sessions_used: list[AsyncSession] = []


class _SessionFactory:
    def __init__(self) -> None:
        self.sessions: list[_Session] = []

    def __call__(self) -> _Session:
        session = _Session()
        self.sessions.append(session)
        return session


class _SessionFactoryOverride(Provider):
    def __init__(self, sessions: _SessionFactory) -> None:
        super().__init__()
        self._sessions = sessions

    @provide(scope=Scope.APP, provides=async_sessionmaker[AsyncSession], override=True)
    def sessions(self) -> async_sessionmaker[AsyncSession]:
        return self._sessions  # type: ignore[return-value]


class _ActionOverrides(Provider):
    def __init__(self, reads: _ResourceReadTracker, *, component: str) -> None:
        super().__init__(component=component)
        self._reads = reads

    @provide(scope=Scope.ACTION, provides=ResourceRepository, override=True)
    def resources(self, session: AsyncSession) -> ResourceRepository:
        reads = _ResourceReads(self._reads)
        reads.session = session
        return reads  # type: ignore[return-value]


def _container(sessions: _SessionFactory, reads: _ResourceReadTracker) -> AsyncContainer:
    settings = Settings(
        database_url="postgresql+psycopg://localhost:1/devops_hub_test",
        token_pepper="test-token-pepper-" * 3,
    )
    return BackendContainer(
        settings,
        overrides=(
            _SessionFactoryOverride(sessions),
            _ActionOverrides(reads, component="platform_action"),
            _AuthorizerOverride(),
        ),
    ).combined()


def test_platform_dispatch_uses_same_session_for_unit_and_repository(monkeypatch) -> None:
    trusted = AccessContext(uuid4(), uuid4(), "developer", frozenset({"resources:read"}))
    membership_sessions = []

    async def project_roles(session, *_args, **_kwargs):
        membership_sessions.append(session)
        return {trusted.project_id: trusted.role}

    monkeypatch.setattr(
        "devops_platform.infra.module.project_roles_for_operation",
        project_roles,
    )
    sessions = _SessionFactory()
    reads = _ResourceReadTracker()
    container = _container(sessions, reads)

    async def exercise() -> ResourceDetails:
        try:
            async with container() as request_container:
                host = await request_container.get(DeveloperPlatformModule)
                return await host.query(ReadResource(trusted, uuid4()))
        finally:
            await container.close()

    result = asyncio.run(exercise())
    assert result.project_id == trusted.project_id
    assert len(sessions.sessions) == 1
    assert membership_sessions == reads.sessions_used == [sessions.sessions[0]]
    assert len(reads.repositories) == 1
    assert reads.repositories[0].session is sessions.sessions[0]
    session = sessions.sessions[0]
    assert session.begins == session.commits == session.closes == 1
    assert session.rollbacks == 0


def test_platform_dispatch_creates_a_fresh_action_unit_for_each_call(monkeypatch) -> None:
    trusted = AccessContext(uuid4(), uuid4(), "developer", frozenset({"resources:read"}))
    membership_sessions = []

    async def project_roles(session, *_args, **_kwargs):
        membership_sessions.append(session)
        return {trusted.project_id: trusted.role}

    monkeypatch.setattr(
        "devops_platform.infra.module.project_roles_for_operation",
        project_roles,
    )
    sessions = _SessionFactory()
    reads = _ResourceReadTracker()
    container = _container(sessions, reads)

    async def exercise() -> tuple[ResourceDetails, ResourceDetails]:
        try:
            async with container() as request_container:
                host = await request_container.get(DeveloperPlatformModule)
                first = await host.query(ReadResource(trusted, uuid4()))
                second = await host.query(ReadResource(trusted, uuid4()))
                return first, second
        finally:
            await container.close()

    first, second = asyncio.run(exercise())
    assert first.id != second.id
    assert len(sessions.sessions) == 2
    assert sessions.sessions[0] is not sessions.sessions[1]
    assert membership_sessions == reads.sessions_used == sessions.sessions
    assert len(reads.repositories) == 2
    assert reads.repositories[0] is not reads.repositories[1]
    assert [repository.session for repository in reads.repositories] == sessions.sessions
    assert all(
        session.begins == session.commits == session.closes == 1 for session in sessions.sessions
    )

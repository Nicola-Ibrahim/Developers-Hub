"""Platform refreshes the authenticated caller role before authorization and dispatch."""

import asyncio
from uuid import uuid4

import pytest
from dishka import Scope

from devops_platform.application.resource_management.get_resource.handler import (
    ReadResourceHandler,
)
from devops_platform.application.resource_management.get_resource.query import (
    ReadResource,
)
from devops_platform.application.shared.errors import CatalogForbidden
from devops_platform.domain.value_objects.access_context import AccessContext
from devops_platform.infra.module import DeveloperPlatformModule
from shared.authorization.models import AuthorizationDecision
from shared.infra.persistence.unit_of_work import SqlAlchemyUnitOfWork


class Authorizer:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        self.requests = []

    async def evaluate(self, request):
        self.requests.append(request)
        return AuthorizationDecision(self.allowed)


def test_http_host_rechecks_trusted_access_and_rolls_back_denial(monkeypatch) -> None:
    project_id = uuid4()
    supplied = AccessContext(uuid4(), project_id, "admin", frozenset({"resources:read"}))
    trusted = AccessContext(supplied.user_id, project_id, "developer", supplied.scopes)
    events: list[str] = []

    class Session:
        async def scalar(self, _statement):
            return None

    class Unit:
        session = Session()

        async def run(self, operation, present):
            try:
                result = await operation()
            except Exception:
                events.append("rollback")
                raise
            events.append("commit")
            return present(result)

    class Container:
        def __call__(self, *, scope):
            assert scope is Scope.ACTION
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, kind, *, component=""):
            if kind is SqlAlchemyUnitOfWork:
                assert component == "platform_action"
                return Unit()
            assert kind is ReadResourceHandler

            class Handler:
                async def execute(self, message):
                    events.append("dispatch")
                    return message.access

            return Handler()

    async def project_roles(_session, actor_id, project_ids, *, membership_target_id):
        assert (actor_id, project_ids, membership_target_id) == (
            trusted.user_id,
            (project_id,),
            None,
        )
        events.append("membership")
        return {project_id: trusted.role}

    monkeypatch.setattr("devops_platform.infra.module.project_roles_for_operation", project_roles)
    host = DeveloperPlatformModule(Container(), Authorizer(False))

    with pytest.raises(CatalogForbidden):
        asyncio.run(host.query(ReadResource(supplied, uuid4())))
    assert events == ["membership", "rollback"]


def test_http_host_preserves_authenticated_actor_and_refreshes_project_role(monkeypatch) -> None:
    project_id = uuid4()
    supplied = AccessContext(uuid4(), project_id, "admin", frozenset({"resources:read"}))
    trusted = AccessContext(supplied.user_id, project_id, "developer", supplied.scopes)
    events: list[str] = []

    class Session:
        async def scalar(self, _statement):
            return None

    class Unit:
        session = Session()

        async def run(self, operation, present):
            result = await operation()
            events.append("commit")
            return present(result)

    class Container:
        def __call__(self, *, scope):
            assert scope is Scope.ACTION
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, kind, *, component=""):
            if kind is SqlAlchemyUnitOfWork:
                assert component == "platform_action"
                return Unit()
            assert kind is ReadResourceHandler

            class Handler:
                async def execute(self, message):
                    events.append("dispatch")
                    return message.access

            return Handler()

    async def project_roles(_session, actor_id, project_ids, *, membership_target_id):
        assert (actor_id, project_ids, membership_target_id) == (
            trusted.user_id,
            (project_id,),
            None,
        )
        events.append("membership")
        return {project_id: trusted.role}

    monkeypatch.setattr("devops_platform.infra.module.project_roles_for_operation", project_roles)
    authorizer = Authorizer(True)
    host = DeveloperPlatformModule(Container(), authorizer)

    assert asyncio.run(host.query(ReadResource(supplied, uuid4()))) == trusted
    assert authorizer.requests[0].subject_id == trusted.user_id
    assert authorizer.requests[0].scopes == ("resources:read",)
    assert events == ["membership", "dispatch", "commit"]

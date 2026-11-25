"""The HTTP host replaces untrusted message claims before platform dispatch."""

import asyncio
from uuid import uuid4

import pytest
from dishka import Scope
from starlette.requests import Request

from api.platform.module import PlatformRequestModule
from devops_platform.application.resource_management.get_resource.handler import (
    ReadResourceHandler,
)
from devops_platform.application.resource_management.get_resource.query import (
    ReadResource,
)
from devops_platform.application.shared.errors import CatalogForbidden
from devops_platform.domain.value_objects.access_context import AccessContext
from identity.domain.interfaces.project_access import IdentityProjectAccess
from shared.infra.persistence.unit_of_work import SqlAlchemyUnitOfWork


def test_http_host_rechecks_trusted_access_and_rolls_back_denial(monkeypatch) -> None:
    project_id = uuid4()
    forged = AccessContext(uuid4(), project_id, "admin", frozenset({"resources:read"}))
    trusted = AccessContext(uuid4(), project_id, "developer", frozenset())
    events: list[str] = []

    class Unit:
        session = object()

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
            if kind is IdentityProjectAccess:
                return object()
            if kind is SqlAlchemyUnitOfWork:
                assert component == "platform_action"
                return Unit()
            assert kind is ReadResourceHandler

            class Handler:
                async def execute(self, message):
                    events.append("dispatch")
                    return message.access

            return Handler()

    async def authenticate(*_args):
        events.append("authenticate")
        return trusted

    monkeypatch.setattr("api.platform.module.authenticate_platform_access", authenticate)
    request = Request({"type": "http", "method": "GET", "path": "/"})
    request.state.request_identity = "private-token"
    host = PlatformRequestModule(Container(), request, object())

    with pytest.raises(CatalogForbidden):
        asyncio.run(host.query(ReadResource(forged, uuid4())))
    assert events == ["authenticate", "rollback"]


def test_http_host_dispatches_with_authenticated_actor_not_message_claims(monkeypatch) -> None:
    project_id = uuid4()
    forged = AccessContext(uuid4(), project_id, "admin", frozenset({"resources:read"}))
    trusted = AccessContext(uuid4(), project_id, "developer", frozenset({"resources:read"}))
    events: list[str] = []

    class Unit:
        session = object()

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
            if kind is IdentityProjectAccess:
                return object()
            if kind is SqlAlchemyUnitOfWork:
                assert component == "platform_action"
                return Unit()
            assert kind is ReadResourceHandler

            class Handler:
                async def execute(self, message):
                    events.append("dispatch")
                    return message.access

            return Handler()

    async def authenticate(*_args):
        events.append("authenticate")
        return trusted

    monkeypatch.setattr("api.platform.module.authenticate_platform_access", authenticate)
    request = Request({"type": "http", "method": "GET", "path": "/"})
    request.state.request_identity = "private-token"
    host = PlatformRequestModule(Container(), request, object())

    assert asyncio.run(host.query(ReadResource(forged, uuid4()))) == trusted
    assert events == ["authenticate", "dispatch", "commit"]

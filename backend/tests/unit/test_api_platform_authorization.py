"""API dispatch is blocked by the typed platform authorization boundary."""

import asyncio
from uuid import uuid4

import pytest
from dishka import Scope

from api.platform.application_delivery.routes import applications
from api.platform.catalog.routes import catalog
from composition.integrations.platform_authorization import DeveloperPlatformModule
from devops_platform.application.shared.dto import AccessContext
from devops_platform.application.shared.errors import CatalogForbidden, PlatformRequestError
from identity.domain.interfaces.project_access import IdentityProjectAccess
from shared.authorization.credentials import RequestCredentials
from shared.authorization.models import AuthorizationDecision
from shared.infra.persistence.unit_of_work import SqlAlchemyUnitOfWork


class RecordingModule:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def query(self, message: object) -> object:
        self.calls.append(message)
        raise AssertionError("business module must not be called for a denied action")

    async def execute(self, message: object) -> object:
        self.calls.append(message)
        raise AssertionError("business module must not be called for a denied action")


class DenyAuthorization:
    async def evaluate(self, request):
        return AuthorizationDecision(False, "unit-test", "scope")


@pytest.mark.parametrize("route", [catalog, applications])
def test_denied_platform_action_does_not_dispatch(route) -> None:
    access = AccessContext(
        user_id=uuid4(),
        project_id=uuid4(),
        role="developer",
        scopes=frozenset(),
    )

    class Unit:
        session = object()

        async def run(self, action, present):
            return present(await action())

    class Container:
        def __init__(self):
            self.handler_resolutions = []

        def __call__(self, *, scope):
            assert scope is Scope.ACTION
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, kind, *, component=""):
            if kind is SqlAlchemyUnitOfWork:
                return Unit()
            if kind is IdentityProjectAccess:
                return object()
            self.handler_resolutions.append(kind)
            return RecordingModule()

    async def authenticate(*_args):
        return access

    from unittest.mock import patch

    handler = route.__dishka_orig_func__
    credentials = RequestCredentials("private-test-token")
    host = DeveloperPlatformModule(Container(), credentials, object(), DenyAuthorization())

    async def invoke() -> None:
        with patch(
            "composition.integrations.platform_authorization.authenticate_platform_access",
            authenticate,
        ):
            with pytest.raises((CatalogForbidden, PlatformRequestError)):
                await handler(access, host)

    asyncio.run(invoke())
    assert host._container.handler_resolutions == []

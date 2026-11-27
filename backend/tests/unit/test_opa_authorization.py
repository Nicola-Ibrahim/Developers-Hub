import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from dishka import Scope
from dishka.exceptions import NoFactoryError

from backend import BackendContainer
from devops_platform.application.applications.create_application.command import (
    ApplicationRegistration,
    CreateApplication,
)
from devops_platform.application.projects.list_projects.query import ReadProjects
from devops_platform.application.resource_management.submit_database_request.command import (
    DatabaseRequest,
    RequestTemporaryDatabase,
)
from devops_platform.application.shared.dto import AccessContext
from devops_platform.application.shared.errors import CatalogForbidden, PlatformRequestError
from devops_platform.application.software_delivery.attach_database.command import (
    AttachDatabase,
    ResourceAttachmentSpec,
)
from devops_platform.application.software_delivery.create_local_preview.command import (
    CreateLocalPreview,
    LocalPreviewRegistration,
)
from devops_platform.application.software_delivery.deploy_application.command import (
    DeployApplication,
    DeploymentSpec,
)
from devops_platform.infra.handlers import PLATFORM_HANDLER_REGISTRY
from devops_platform.infra.module import DeveloperPlatformModule
from identity.application.interfaces.security import TokenHasher
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.records import ApiTokenStatus, MembershipDetails, SessionPrincipal
from identity.infra.module import IDENTITY_HANDLER_REGISTRY, IdentityModule
from shared.authorization.credentials import RequestCredentials, SessionCredentials
from shared.authorization.dispatch import operation_id, require_authorized
from shared.authorization.interfaces import (
    AuthorizationDecisionPort,
    AuthorizationDenied,
    AuthorizationUnavailable,
)
from shared.authorization.models import AuthorizationDecision, AuthorizationRequest
from shared.dispatch import Command
from shared.infra.authorization.opa_client import OpaAuthorizationClient
from shared.infra.persistence.unit_of_work import SqlAlchemyUnitOfWork
from shared.infra.settings import Settings

EXEMPT_OPERATIONS = {
    "LoginCommand",
    "AuthenticateSessionQuery",
    "AuthenticateApiTokenQuery",
    "ReadTemplates",
}
REGISTERED_OPERATIONS = [
    (registry, message)
    for registry in (IDENTITY_HANDLER_REGISTRY, PLATFORM_HANDLER_REGISTRY)
    for message in (*registry.commands, *registry.queries)
]


def request() -> AuthorizationRequest:
    return AuthorizationRequest(
        subject_id=uuid4(),
        action="database:read",
        resource_kind="database",
        project_id=uuid4(),
        role="developer",
        scopes=("resource:read",),
    )


@pytest.mark.parametrize("allowed", [True, False])
def test_returns_opa_allow_or_deny(allowed: bool) -> None:
    seen: list[httpx.Request] = []

    def respond(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(
            200,
            json={
                "result": {
                    "allow": allowed,
                    "policy_revision": "r1",
                    "reason": None if allowed else "ownership",
                }
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await OpaAuthorizationClient("http://opa:8181", client).evaluate(request())

    result = asyncio.run(run())

    assert result.allowed is allowed
    assert result.policy_revision == "r1"
    assert result.reason == (None if allowed else "ownership")
    assert seen[0].url.path == "/v1/data/devops/authorization/decision"
    assert b"database:read" in seen[0].content


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"result": {}},
        {"result": {"allow": "true"}},
        {"result": {"allow": True}},
        {"result": {"allow": False, "policy_revision": "r1", "reason": []}},
    ],
)
def test_missing_or_malformed_decision_fails_closed(body: dict[str, object]) -> None:
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
        ) as client:
            with pytest.raises(AuthorizationUnavailable):
                await OpaAuthorizationClient("http://opa:8181", client).evaluate(request())

    asyncio.run(run())


def test_transport_failure_is_sanitized() -> None:
    async def run(error_type):
        async def fail(_: httpx.Request) -> httpx.Response:
            raise error_type("sensitive endpoint detail")

        async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
            with pytest.raises(AuthorizationUnavailable) as error:
                await OpaAuthorizationClient("http://opa:8181", client).evaluate(request())
        return error.value

    for error_type in (httpx.ConnectError, httpx.ReadTimeout):
        error = asyncio.run(run(error_type))
        assert "sensitive endpoint detail" not in str(error)


def test_dispatch_uses_qualified_message_type_and_preserves_denial():
    class Update:
        pass

    class Decisions:
        async def evaluate(self, facts):
            seen.append(facts)
            return AuthorizationDecision(False, "test")

    seen = []
    denied = PermissionError("operation-specific denial")
    with pytest.raises(PermissionError) as error:
        asyncio.run(require_authorized(Decisions(), Update(), request(), denied))
    assert error.value is denied
    assert [facts.action for facts in seen] == [operation_id(Update)]
    assert operation_id(Update) == f"{Update.__module__}.{Update.__qualname__}"


def test_registered_operations_have_unique_ids_and_explicit_policy_coverage():
    operations = [message for _, message in REGISTERED_OPERATIONS]
    identifiers = [operation_id(message) for message in operations]
    assert len(identifiers) == len(set(identifiers))
    assert len(identifiers) == len(set(operations))

    assert EXEMPT_OPERATIONS <= {message.__name__ for message in operations}
    protected = {
        operation_id(message) for message in operations if message.__name__ not in EXEMPT_OPERATIONS
    }
    policy_dir = Path(__file__).resolve().parents[3] / "ops" / "policies"
    policy_ids = {
        match
        for policy in policy_dir.glob("*.rego")
        for match in re.findall(r'"((?:identity|devops_platform)\.[\w.]+)"', policy.read_text())
    }
    assert protected <= policy_ids
    assert policy_ids <= set(identifiers)


@pytest.mark.parametrize(
    ("registry", "message_type", "empty_projects"),
    [
        pytest.param(registry, message, False, id=message.__name__)
        for registry, message in REGISTERED_OPERATIONS
        if message.__name__ not in EXEMPT_OPERATIONS
    ]
    + [pytest.param(PLATFORM_HANDLER_REGISTRY, ReadProjects, True, id="ReadProjects-empty")],
)
@pytest.mark.parametrize("outcome", ["deny", "unavailable", "invalid"])
def test_all_protected_operations_stop_at_the_policy_boundary(
    registry, message_type, empty_projects, outcome, monkeypatch
):
    actor_id, project_id, object_id = uuid4(), uuid4(), uuid4()
    scopes = frozenset({"catalog:read", "resources:read", "resources:write", "connections:read"})
    access = AccessContext(actor_id, project_id, "admin", scopes)
    principal = SessionPrincipal(
        actor_id,
        "tester",
        object_id,
        project_id,
        "project",
        "admin",
        tuple(scopes),
        (MembershipDetails(project_id, "project", "admin"),),
        "",
    )
    requests = {
        RequestTemporaryDatabase: DatabaseRequest(
            project_id, object_id, "test-db", "postgres", "16", "local", "small", 3600
        ),
        CreateApplication: ApplicationRegistration(
            object_id, "test-app", "python-fastapi", "1.0.0"
        ),
        CreateLocalPreview: LocalPreviewRegistration("test-preview", object_id, 3600),
        AttachDatabase: ResourceAttachmentSpec("postgres", "16", "local", "small", 3600),
        DeployApplication: DeploymentSpec("sha256:" + "a" * 64),
    }
    now = datetime.now(UTC)
    inputs = {
        "access": access,
        "accesses": () if empty_projects else (access,),
        "user_id": actor_id if message_type is ReadProjects else object_id,
        "actor_id": actor_id,
        "actor_name": "test-actor",
        "current_password": "test-current-password",
        "new_password": "test-replacement-password",
        "session_token": "session",
        "project_id": project_id,
        "request": requests.get(message_type),
        "now": now,
        "expires_at": now,
        "name": "test-token",
        "scopes": tuple(scopes),
        "hours": 1,
        "idempotency_key": "test-operation",
        "expected_revision": 1,
        "limit": 25,
        "raw_body": b"{}",
        "signature": None,
        "delivery_id": "ab01-2345-6789-0123",
        "event": "pull_request",
        "display_name": None,
        "role": "admin",
    }
    # Construct valid messages so every outcome reaches the authorization boundary.
    message = message_type(
        **{
            name: inputs.get(name, object_id if name.endswith("_id") else None)
            for name, field in message_type.model_fields.items()
            if field.is_required()
        }
    )
    calls = []

    class Decisions:
        async def evaluate(self, facts):
            calls.append(facts.action)
            if empty_projects:
                assert facts.subject_id == actor_id
                assert facts.project_id is None
            if outcome == "unavailable":
                raise AuthorizationUnavailable()
            if outcome == "invalid":
                return None
            return AuthorizationDecision(False, "test")

    class BoundaryFixtures:
        session = None

        async def authorize_session_operation(self, *_args, **_kwargs):
            return principal

        async def validate_csrf(self, *_args):
            return True

        async def scalar(self, _):
            return SimpleNamespace(id=object_id, owner_id=actor_id, project_id=project_id)

        async def execute(self, _):
            row = await self.scalar(None)
            return SimpleNamespace(first=lambda: row)

        async def run(self, action, materialize):
            return materialize(await action())

        async def lock_personal_token(self, token_id, *, user_id):
            return ApiTokenStatus(token_id, user_id, project_id, None)

        def __call__(self, *, scope):
            assert scope is Scope.ACTION
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, dependency, *, component=""):
            if dependency is TokenHasher:
                return SimpleNamespace(digest=str)
            if dependency is AuthorizationDecisionPort:
                return decisions
            if dependency in (
                SqlAlchemyUnitOfWork,
                SessionRepository,
                ApiTokenRepository,
            ):
                return self
            if dependency.__name__ == "ChangePasswordHandler":
                return SimpleNamespace(execute=check_password_write_guard)
            if dependency.__name__ == "ProcessGithubPreviewWebhookHandler":
                return SimpleNamespace(verify_signature=lambda _: object())
            pytest.fail(f"Resolved a business handler before authorization: {dependency}")

    async def check_password_write_guard(_command, precondition):
        await precondition(fixtures, None)
        pytest.fail("Reached password mutation without authorization")

    fixtures = BoundaryFixtures()
    fixtures.session = fixtures
    decisions = Decisions()
    denied = (AuthorizationDenied, CatalogForbidden, PlatformRequestError)
    if registry is IDENTITY_HANDLER_REGISTRY:
        credentials = RequestCredentials(
            SessionCredentials(
                getattr(message, "session_token", None) or "session", csrf_token="csrf"
            )
        )
        identity = IdentityModule(fixtures, credentials)
        dispatch = identity.execute if isinstance(message, Command) else identity.query
        operation = dispatch(message)
    else:

        async def membership_roles(*_args, **_kwargs):
            return {project_id: access.role}

        monkeypatch.setattr(
            "devops_platform.infra.module.project_roles_for_operation",
            membership_roles,
        )
        host = DeveloperPlatformModule(fixtures, decisions)
        dispatch = host.execute if isinstance(message, Command) else host.query
        operation = dispatch(message)

    with pytest.raises(denied if outcome == "deny" else AuthorizationUnavailable):
        asyncio.run(operation)
    assert calls == [operation_id(message)]


def test_platform_protected_handlers_are_not_injectable_in_request_scope():
    settings = Settings(
        database_url="postgresql+psycopg://localhost:1/devops_hub_test",
        token_pepper="test-only-auth-pepper-" * 3,
    )
    handlers = {
        handler
        for registrations in (PLATFORM_HANDLER_REGISTRY.commands, PLATFORM_HANDLER_REGISTRY.queries)
        for message, handler in registrations.items()
        if message.__name__ not in EXEMPT_OPERATIONS
    }

    async def verify():
        container = BackendContainer(settings).api()
        try:
            async with container() as request_scope:
                for handler in handlers:
                    with pytest.raises(NoFactoryError):
                        await request_scope.get(handler)
        finally:
            await container.close()

    asyncio.run(verify())


def test_credentials_are_isolated_to_one_request_scope():
    settings = Settings(
        database_url="postgresql+psycopg://localhost:1/devops_hub_test",
        token_pepper="test-only-auth-pepper-" * 3,
    )

    async def verify():
        container = BackendContainer(settings).api()
        try:
            async with container() as first, container() as second:
                credentials = await first.get(RequestCredentials)
                credentials.identity = "test-credential"
                assert await first.get(RequestCredentials) is credentials
                assert (await second.get(RequestCredentials)).identity is None
        finally:
            await container.close()

    asyncio.run(verify())


def test_platform_rejects_unknown_operations_before_opening_an_action_scope():
    @dataclass(frozen=True)
    class UnknownCommand(Command[None]):
        access: AccessContext

    access = AccessContext(uuid4(), uuid4(), "developer", frozenset())
    host = DeveloperPlatformModule(object(), object())
    with pytest.raises(TypeError, match="[Uu]n(registered|supported)"):
        asyncio.run(host.execute(UnknownCommand(access)))

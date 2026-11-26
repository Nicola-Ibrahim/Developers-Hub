import asyncio
import re
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from shared.authorization.dispatch import operation_id, require_authorized
from shared.authorization.interfaces import AuthorizationUnavailable
from shared.authorization.models import AuthorizationDecision, AuthorizationRequest
from shared.infra.authorization.opa_client import OpaAuthorizationClient


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
    from devops_platform.infra.composition.module import PLATFORM_HANDLER_REGISTRY
    from identity.infra.composition.module import IDENTITY_HANDLER_REGISTRY

    registries = (IDENTITY_HANDLER_REGISTRY, PLATFORM_HANDLER_REGISTRY)
    operations = [
        message for registry in registries for message in (*registry.commands, *registry.queries)
    ]
    identifiers = [operation_id(message) for message in operations]
    assert len(identifiers) == len(set(identifiers))
    assert len(identifiers) == len(set(operations))

    exempt = {
        "LoginCommand",
        "AuthenticateSessionQuery",
        "AuthenticateApiTokenQuery",
        "ReadTemplates",
    }
    assert exempt <= {message.__name__ for message in operations}
    protected = {operation_id(message) for message in operations if message.__name__ not in exempt}
    policy_dir = Path(__file__).resolve().parents[3] / "ops" / "policies"
    policy_ids = {
        match
        for policy in policy_dir.glob("*.rego")
        for match in re.findall(r'"((?:identity|devops_platform)\.[\w.]+)"', policy.read_text())
    }
    assert protected <= policy_ids
    assert policy_ids <= set(identifiers)

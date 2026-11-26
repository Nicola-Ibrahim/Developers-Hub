"""Platform authorization facts use trusted access and the shared dispatch contract."""

import asyncio
from uuid import uuid4

import pytest

from devops_platform.application.projects.get_project.query import ReadProject
from devops_platform.application.projects.list_projects.query import ReadProjects
from devops_platform.application.resource_management.read_connection.query import (
    ReadDatabaseConnection,
)
from devops_platform.application.shared.errors import CatalogForbidden
from devops_platform.authorization import ALL_SCOPES, authorization_facts
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.authorization.dispatch import operation_id, require_authorized
from shared.authorization.models import AuthorizationDecision


class Authorizer:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        self.requests = []

    async def evaluate(self, request):
        self.requests.append(request)
        return AuthorizationDecision(self.allowed)


def test_all_scopes_remains_the_token_vocabulary() -> None:
    assert ALL_SCOPES == (
        "catalog:read",
        "resources:read",
        "resources:write",
        "connections:read",
    )


def test_request_uses_shared_operation_id_and_trusted_envelope() -> None:
    access = AccessContext(uuid4(), uuid4(), "developer", frozenset({"resources:read"}))
    message = ReadProject(access, access.project_id)
    facts = authorization_facts(message, access)
    authorizer = Authorizer(True)

    asyncio.run(require_authorized(authorizer, message, facts, CatalogForbidden()))

    assert authorizer.requests[0].action == operation_id(message)
    assert authorizer.requests[0].subject_id == access.user_id
    assert authorizer.requests[0].subject_project_id == access.project_id
    assert authorizer.requests[0].project_id == access.project_id


def test_shared_denial_raises_the_transport_contract_exception() -> None:
    access = AccessContext(uuid4(), uuid4(), "developer", frozenset())
    message = ReadDatabaseConnection(access, uuid4())
    authorizer = Authorizer(False)

    with pytest.raises(CatalogForbidden):
        asyncio.run(
            require_authorized(
                authorizer, message, authorization_facts(message), CatalogForbidden()
            )
        )


def test_read_projects_facts_can_be_built_for_each_distinct_subject_project() -> None:
    project_id = uuid4()
    access = AccessContext(uuid4(), project_id, "developer", frozenset(ALL_SCOPES))
    message = ReadProjects((access,))
    facts = authorization_facts(message, access, project_id=project_id)
    assert facts.resource_kind == "projects"
    assert facts.project_id == project_id
    assert facts.subject_id == access.user_id

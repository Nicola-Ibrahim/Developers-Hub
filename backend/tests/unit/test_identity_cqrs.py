import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from devops_platform.application.project_access.list_project_members.handler import (
    ListProjectMembersHandler,
)
from devops_platform.application.project_access.list_project_members.query import ListProjectMembers
from devops_platform.application.project_access.manage_project_membership.command import (
    ManageProjectMembership,
)
from devops_platform.application.project_access.manage_project_membership.handler import (
    ManageProjectMembershipHandler,
)
from devops_platform.application.shared.dto import AccessContext
from devops_platform.domain.errors import InvalidProjectRole
from identity.application.accounts.create_user.command import CreateUserCommand
from identity.application.accounts.create_user.handler import CreateUserHandler
from identity.application.authentication.authenticate_session.handler import (
    AuthenticateSessionHandler,
)
from identity.application.authentication.authenticate_session.query import AuthenticateSessionQuery
from identity.domain.records import SessionPrincipal

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class Transaction:
    def __init__(self, repository):
        self.repository = repository

    async def run(self, action):
        return await action(self.repository, None)


class Passwords:
    def hash(self, password: str) -> str:
        return f"encoded:{password}"

    def verify(self, password: str, encoded: str) -> bool:
        return encoded == f"encoded:{password}"


def test_create_internal_user_handler_builds_normalized_domain_name() -> None:
    class Repository:
        async def create_user(self, user_name, password_hash, actor_id, now):
            self.values = (user_name, password_hash, actor_id, now)
            return uuid4()

    repository = Repository()
    asyncio.run(
        CreateUserHandler(Transaction(repository), Passwords(), lambda: NOW).execute(
            CreateUserCommand(" Developer ", "long-enough-password")
        )
    )

    assert repository.values[:2] == ("developer", "encoded:long-enough-password")


def test_membership_command_validates_project_role_before_persistence() -> None:
    class Repository:
        async def set_membership(self, **values):
            raise AssertionError(f"unexpected persistence call: {values}")

    actor_id, project_id = uuid4(), uuid4()
    with pytest.raises(InvalidProjectRole, match="role"):
        asyncio.run(
            ManageProjectMembershipHandler(Repository()).execute(
                ManageProjectMembership(
                    AccessContext(actor_id, project_id, "admin", frozenset({"resources:write"})),
                    project_id,
                    uuid4(),
                    "owner",
                    NOW,
                )
            )
        )


def test_project_member_query_is_read_only_and_receives_authorized_actor() -> None:
    actor_id, project_id = uuid4(), uuid4()

    class ReadRepository:
        async def list_project_members(self, *, actor_id, project_id):
            self.values = (actor_id, project_id)
            return ()

    repository = ReadRepository()
    result = asyncio.run(
        ListProjectMembersHandler(repository).execute(
            ListProjectMembers(
                AccessContext(actor_id, project_id, "admin", frozenset({"resources:read"})),
                project_id,
            )
        )
    )

    assert result == ()
    assert repository.values == (actor_id, project_id)


def test_session_refresh_is_explicitly_a_command() -> None:
    user_id, session_id = uuid4(), uuid4()
    principal = SessionPrincipal(user_id, "dev", session_id, None, None, None, (), (), "")

    class Repository:
        async def authenticate_session(self, **values):
            self.values = values
            return principal, "encoded-token"

    repository = Repository()
    result = asyncio.run(
        AuthenticateSessionHandler(
            repository, lambda: NOW, lambda value: f"digest:{value}"
        ).execute(AuthenticateSessionQuery("private-session"))
    )

    assert result == principal
    assert repository.values == {
        "token_digest": "digest:private-session",
        "project_id": None,
        "now": NOW,
    }
    assert "private-session" not in repr(AuthenticateSessionQuery("private-session"))

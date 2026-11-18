"""Project member administration messages and handlers."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from devops_platform.application.project_access.manage_membership import set_membership
from devops_platform.application.shared.dto import AccessContext
from shared.dispatch import Command, Query

ProjectMemberDetails = tuple[UUID, str, str, bool]


class ProjectAccessRepository(Protocol):
    async def bootstrap_first_project_admin(
        self, *, user_id: UUID, project_id: UUID, now: datetime
    ) -> None: ...

    async def set_membership(
        self,
        *,
        actor_id: UUID,
        user_id: UUID,
        project_id: UUID,
        role: str | None,
        now: datetime,
    ) -> None: ...

    async def list_project_members(
        self, *, actor_id: UUID, project_id: UUID
    ) -> tuple[ProjectMemberDetails, ...]: ...


@dataclass(frozen=True, slots=True)
class ManageProjectMembership(Command[None]):
    access: AccessContext
    project_id: UUID
    user_id: UUID
    role: str | None


@dataclass(frozen=True, slots=True)
class ListProjectMembers(Query[tuple[ProjectMemberDetails, ...]]):
    access: AccessContext
    project_id: UUID


class ManageProjectMembershipHandler:
    def __init__(self, repository: ProjectAccessRepository, clock: Callable[[], datetime]) -> None:
        self.repository = repository
        self.clock = clock

    async def execute(self, command: ManageProjectMembership) -> None:
        await set_membership(
            self.repository,
            actor_id=command.access.user_id,
            user_id=command.user_id,
            project_id=command.project_id,
            role=command.role,
            now=self.clock(),
        )


class ListProjectMembersHandler:
    def __init__(self, repository: ProjectAccessRepository) -> None:
        self.repository = repository

    async def execute(self, query: ListProjectMembers) -> tuple[ProjectMemberDetails, ...]:
        return await self.repository.list_project_members(
            actor_id=query.access.user_id, project_id=query.project_id
        )

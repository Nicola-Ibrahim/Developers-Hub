from datetime import datetime
from typing import Protocol
from uuid import UUID

from devops_platform.application.project_access.list_project_members.query import (
    ProjectMemberDetails,
)


class ProjectAccessRepository(Protocol):
    async def bootstrap_first_project_admin(
        self, *, user_id: UUID, project_id: UUID, now: datetime
    ) -> None: ...
    async def set_membership(
        self, *, actor_id: UUID, user_id: UUID, project_id: UUID, role: str | None, now: datetime
    ) -> None: ...
    async def list_project_members(
        self, *, actor_id: UUID, project_id: UUID
    ) -> tuple[ProjectMemberDetails, ...]: ...

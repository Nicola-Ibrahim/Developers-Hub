from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from devops_platform.application.project_access.list_project_members.query import (
    ProjectMemberDetails,
)


class ProjectAccessRepository(ABC):
    @abstractmethod
    async def bootstrap_first_project_admin(
        self, *, user_id: UUID, project_id: UUID, now: datetime
    ) -> None: ...
    @abstractmethod
    async def set_membership(
        self, *, actor_id: UUID, user_id: UUID, project_id: UUID, role: str | None, now: datetime
    ) -> None: ...
    @abstractmethod
    async def list_project_members(
        self, *, project_id: UUID
    ) -> tuple[ProjectMemberDetails, ...]: ...

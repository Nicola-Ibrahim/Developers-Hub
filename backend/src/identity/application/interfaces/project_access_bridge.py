"""Host composition operations for Identity's transactional project-access adapters."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from identity.application.interfaces.browser_transactions import BrowserRepository
from identity.domain.records import ProjectMemberDetails


class ProjectAccessBridge(Protocol):
    async def set_membership(
        self,
        repository: BrowserRepository,
        *,
        actor_id: UUID,
        user_id: UUID,
        project_id: UUID,
        role: str | None,
        now: datetime,
    ) -> None: ...

    async def list_project_members(
        self, repository: BrowserRepository, *, actor_id: UUID, project_id: UUID
    ) -> tuple[ProjectMemberDetails, ...]: ...

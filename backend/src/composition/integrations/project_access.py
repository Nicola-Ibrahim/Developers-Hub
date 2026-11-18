"""Adapt Identity transaction operations to DeveloperPlatform project-access use cases."""

from datetime import datetime
from uuid import UUID

from devops_platform.application.project_access.manage_membership import set_membership
from devops_platform.domain.errors import InvalidProjectRole
from identity.application.interfaces.browser_transactions import BrowserRepository
from identity.domain.errors import IdentityValidationError
from identity.domain.records import ProjectMemberDetails


class ProjectAccessApplicationBridge:
    async def list_project_members(
        self, repository: BrowserRepository, *, actor_id: UUID, project_id: UUID
    ) -> tuple[ProjectMemberDetails, ...]:
        return await repository.list_project_members(actor_id=actor_id, project_id=project_id)

    async def set_membership(
        self,
        repository: BrowserRepository,
        *,
        actor_id: UUID,
        user_id: UUID,
        project_id: UUID,
        role: str | None,
        now: datetime,
    ) -> None:
        try:
            await set_membership(
                repository,
                actor_id=actor_id,
                user_id=user_id,
                project_id=project_id,
                role=role,
                now=now,
            )
        except InvalidProjectRole as error:
            raise IdentityValidationError(error.message) from error

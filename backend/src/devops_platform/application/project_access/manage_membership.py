"""Project membership mutation use case."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from devops_platform.domain.value_objects.project_role import ProjectRole


class MembershipRepository(Protocol):
    async def set_membership(
        self,
        *,
        actor_id: UUID,
        user_id: UUID,
        project_id: UUID,
        role: str | None,
        now: datetime,
    ) -> None: ...


async def set_membership(
    repository: MembershipRepository,
    *,
    actor_id: UUID,
    user_id: UUID,
    project_id: UUID,
    role: str | None,
    now: datetime,
) -> None:
    validated_role = ProjectRole.parse(role).value if role is not None else None
    await repository.set_membership(
        actor_id=actor_id,
        user_id=user_id,
        project_id=project_id,
        role=validated_role,
        now=now,
    )

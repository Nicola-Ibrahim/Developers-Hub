"""Project access capabilities used by Identity persistence workflows."""

from typing import Protocol
from uuid import UUID

from identity.domain.aggregates.api_token import ApiTokenAuthenticationDetails


class IdentityProjectAccess(Protocol):
    async def project_memberships(self, user_id: UUID) -> tuple[tuple[UUID, str, str], ...]: ...

    async def lock_user_project_access(
        self, user_id: UUID, additional_project_ids: tuple[UUID, ...] = ()
    ) -> tuple[UUID, ...] | None: ...

    async def project_membership_role(self, user_id: UUID, project_id: UUID) -> str | None: ...

    async def lock_named_project(self, name: str) -> UUID | None: ...

    async def lock_project_membership(self, user_id: UUID, project_id: UUID) -> bool: ...

    async def find_token_credential(self, digest: str) -> ApiTokenAuthenticationDetails | None: ...

    async def lock_account_projects(self, user_id: UUID) -> tuple[UUID, ...]: ...

    async def deactivation_conflict(
        self, user_id: UUID, locked_project_ids: tuple[UUID, ...]
    ) -> str | None: ...

    async def demote_admin_memberships(self, user_id: UUID) -> None: ...

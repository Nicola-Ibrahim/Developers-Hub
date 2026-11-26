"""Project access capabilities used by Identity persistence workflows."""

from abc import ABC, abstractmethod
from uuid import UUID


class IdentityProjectAccess(ABC):
    @abstractmethod
    async def project_memberships(self, user_id: UUID) -> tuple[tuple[UUID, str, str], ...]: ...

    @abstractmethod
    async def lock_user_project_access(
        self, user_id: UUID, additional_project_ids: tuple[UUID, ...] = ()
    ) -> tuple[UUID, ...] | None: ...

    @abstractmethod
    async def project_membership_role(self, user_id: UUID, project_id: UUID) -> str | None: ...

    @abstractmethod
    async def lock_project_membership_role(
        self, user_id: UUID, project_id: UUID, *, shared: bool
    ) -> str | None: ...

    @abstractmethod
    async def lock_account_projects(self, user_id: UUID) -> tuple[UUID, ...]: ...

    @abstractmethod
    async def deactivation_conflict(
        self, user_id: UUID, locked_project_ids: tuple[UUID, ...]
    ) -> str | None: ...

    @abstractmethod
    async def demote_admin_memberships(self, user_id: UUID) -> None: ...

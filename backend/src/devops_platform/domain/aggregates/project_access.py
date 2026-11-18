"""Project access rules shared by membership and account lifecycle workflows."""

from dataclasses import dataclass
from uuid import UUID

from devops_platform.domain.errors import DomainError


@dataclass(frozen=True, slots=True)
class ProjectAccess:
    """Project access decisions made from membership and account facts."""

    active_admin_count: int

    def may_remove_active_admin(self, *, removing_admin: bool) -> bool:
        """Whether removing this active admin leaves the project with an admin."""
        return not removing_admin or self.active_admin_count > 1

    def require_membership_change(
        self, *, actor_id: UUID, member_id: UUID, current_role: str | None, role: str | None
    ) -> None:
        if role == "admin":
            return
        if actor_id == member_id:
            raise DomainError("Ask another project administrator to change your role")
        if not self.may_remove_active_admin(removing_admin=current_role == "admin"):
            raise DomainError("A project must retain at least one administrator")

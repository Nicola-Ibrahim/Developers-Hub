"""Project access rules shared by membership and account lifecycle workflows."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProjectAccess:
    """A project-wide access invariant: every project retains an active admin."""

    active_admin_count: int

    def may_remove_active_admin(self) -> bool:
        return self.active_admin_count > 1

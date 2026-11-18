"""Bootstrap the first administrator for a project."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from devops_platform.application.project_access.manage_project_membership import (
    ProjectAccessRepository,
)
from shared.application.interfaces.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class BootstrapFirstAdmin:
    user_id: UUID
    project_id: UUID


class BootstrapFirstAdminHandler:
    def __init__(
        self,
        repository: ProjectAccessRepository,
        unit: UnitOfWork,
        clock: Callable[[], datetime],
    ) -> None:
        self.repository = repository
        self.unit = unit
        self.clock = clock

    async def execute(self, command: BootstrapFirstAdmin) -> None:
        await self.unit.run(
            lambda: self.repository.bootstrap_first_project_admin(
                user_id=command.user_id,
                project_id=command.project_id,
                now=self.clock(),
            ),
            lambda result: result,
        )

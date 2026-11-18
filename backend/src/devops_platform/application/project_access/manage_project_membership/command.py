from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from devops_platform.application.shared.dto import AccessContext
from shared.dispatch import Command


@dataclass(frozen=True, slots=True)
class ManageProjectMembership(Command[None]):
    access: AccessContext
    project_id: UUID
    user_id: UUID
    role: str | None
    now: datetime

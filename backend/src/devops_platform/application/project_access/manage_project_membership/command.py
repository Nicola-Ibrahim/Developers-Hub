from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from devops_platform.application.shared.dto import AccessContext
from devops_platform.domain.value_objects.project_role import ProjectRole
from shared.dispatch import Command


class ManageProjectMembership(BaseModel, Command[None]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    access: AccessContext
    project_id: UUID
    user_id: UUID
    role: str | None
    now: datetime

    @model_validator(mode="after")
    def _validate(self) -> "ManageProjectMembership":
        if self.role is not None:
            ProjectRole.parse(self.role)
        return self

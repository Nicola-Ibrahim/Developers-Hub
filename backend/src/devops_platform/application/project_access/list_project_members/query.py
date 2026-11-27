from uuid import UUID

from pydantic import BaseModel, ConfigDict

from devops_platform.application.shared.dto import AccessContext
from shared.dispatch import Query

type ProjectMemberDetails = tuple[UUID, str, str, bool]


class ListProjectMembers(BaseModel, Query[tuple[ProjectMemberDetails, ...]]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    access: AccessContext
    project_id: UUID

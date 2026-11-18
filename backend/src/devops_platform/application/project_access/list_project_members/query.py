from dataclasses import dataclass
from uuid import UUID

from devops_platform.application.shared.dto import AccessContext
from shared.dispatch import Query

type ProjectMemberDetails = tuple[UUID, str, str, bool]


@dataclass(frozen=True, slots=True)
class ListProjectMembers(Query[tuple[ProjectMemberDetails, ...]]):
    access: AccessContext
    project_id: UUID

"""A role assigned to a project member."""

from dataclasses import dataclass
from typing import Literal

from devops_platform.domain.errors import InvalidProjectRole

ProjectRoleValue = Literal["developer", "admin"]


@dataclass(frozen=True, slots=True)
class ProjectRole:
    value: ProjectRoleValue

    @classmethod
    def parse(cls, value: str) -> "ProjectRole":
        if value not in {"developer", "admin"}:
            raise InvalidProjectRole()
        return cls(value)  # type: ignore[arg-type]

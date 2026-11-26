"""Project and team references required by project registration."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ProjectAccessReferences:
    project_id: UUID
    team_id: UUID


class ProjectAccessDirectory(ABC):
    @abstractmethod
    async def register_references(
        self, project_name: str, team_name: str
    ) -> ProjectAccessReferences: ...

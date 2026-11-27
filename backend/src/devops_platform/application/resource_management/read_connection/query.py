from dataclasses import dataclass, field
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Query


@dataclass(frozen=True)
class DatabaseConnection:
    connection_string: str = field(repr=False)
    host: str
    port: int
    database: str
    user: str
    instructions: str


class ReadDatabaseConnection(BaseModel, Query[DatabaseConnection]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    access: AccessContext
    resource_id: UUID

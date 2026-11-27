from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from devops_platform.application.resource_management.read_models import ResourceDetails
from devops_platform.application.shared.errors import PlatformRequestError
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Query


class ReadResources(BaseModel, Query[tuple[ResourceDetails, ...]]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    access: AccessContext
    project_id: UUID
    after: UUID | None
    limit: int

    @field_validator("limit", mode="before")
    @classmethod
    def _validate_limit(cls, value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
            raise PlatformRequestError("invalid_page", "Page limit must be between 1 and 100", 422)
        return value

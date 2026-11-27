from datetime import datetime, timedelta
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from devops_platform.application.interfaces.resources import ResourceSnapshot
from devops_platform.domain.errors import DomainError, LeaseViolation
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Command


class RenewDatabase(BaseModel, Command[ResourceSnapshot]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    access: AccessContext
    resource_id: UUID
    expected_revision: int
    expires_at: datetime

    @field_validator("expected_revision", mode="before")
    @classmethod
    def _validate_revision(cls, value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise DomainError("Resource revision must be a positive integer.")
        return value

    @field_validator("expires_at")
    @classmethod
    def _validate_expiry(cls, value: datetime) -> datetime:
        offset = value.utcoffset()
        if offset is None:
            raise LeaseViolation("requested_expiry must be a timezone-aware UTC datetime.")
        if offset != timedelta(0):
            raise LeaseViolation("requested_expiry must use UTC.")
        return value

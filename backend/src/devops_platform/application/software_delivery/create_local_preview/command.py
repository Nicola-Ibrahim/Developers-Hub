from dataclasses import dataclass
from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from devops_platform.application.shared.errors import PlatformRequestError
from devops_platform.application.software_delivery.shared.models import WorkloadDetails
from devops_platform.application.software_delivery.shared.policy import (
    APP_NAME,
    IDEMPOTENCY,
)
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Command


@dataclass(frozen=True, slots=True)
class LocalPreviewRegistration:
    name: str
    environment_id: UUID
    ttl_seconds: int


class CreateLocalPreview(BaseModel, Command[tuple[WorkloadDetails, bool]]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    access: AccessContext
    request: LocalPreviewRegistration
    idempotency_key: str
    now: datetime

    @model_validator(mode="after")
    def validate_input(self) -> Self:
        if not IDEMPOTENCY.fullmatch(self.idempotency_key):
            raise PlatformRequestError("invalid_idempotency_key", "Idempotency-Key is invalid", 422)
        request = self.request
        if not APP_NAME.fullmatch(request.name):
            raise PlatformRequestError("invalid_workload_name", "Workload name is invalid", 422)
        if type(request.ttl_seconds) is not int or not 60 <= request.ttl_seconds <= 86400:
            raise PlatformRequestError("invalid_lease", "Preview lifetime is outside policy", 422)
        return self

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from devops_platform.application.shared.errors import PlatformRequestError
from devops_platform.application.software_delivery.shared.models import ApplicationDetails
from devops_platform.application.software_delivery.shared.policy import (
    APP_NAME,
    IDEMPOTENCY,
    IDENTIFIER,
)
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Command


@dataclass(frozen=True)
class ApplicationRegistration:
    environment_id: UUID
    name: str
    template_id: str
    template_version: str


class CreateApplication(BaseModel, Command[tuple[ApplicationDetails, bool]]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    access: AccessContext
    request: ApplicationRegistration
    idempotency_key: str
    now: datetime

    @model_validator(mode="after")
    def validate_input(self) -> Self:
        if not IDEMPOTENCY.fullmatch(self.idempotency_key):
            raise PlatformRequestError("invalid_idempotency_key", "Idempotency-Key is invalid", 422)
        request = self.request
        if not APP_NAME.fullmatch(request.name):
            raise PlatformRequestError("invalid_workload_name", "Workload name is invalid", 422)
        if not IDENTIFIER.fullmatch(request.template_id):
            raise PlatformRequestError("invalid_template", "Template identifier is invalid", 422)
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", request.template_version):
            raise PlatformRequestError("invalid_template", "Template version is invalid", 422)
        return self

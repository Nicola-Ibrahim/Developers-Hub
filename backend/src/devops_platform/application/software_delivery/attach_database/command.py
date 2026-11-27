import re
from dataclasses import dataclass
from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from devops_platform.application.shared.errors import PlatformRequestError
from devops_platform.application.software_delivery.shared.models import DeliveryStepDetails
from devops_platform.application.software_delivery.shared.policy import (
    IDEMPOTENCY,
    IDENTIFIER,
)
from devops_platform.domain.value_objects.access_context import AccessContext
from shared.dispatch import Command


@dataclass(frozen=True)
class ResourceAttachmentSpec:
    template_id: str
    version: str
    target_id: str
    size_id: str
    ttl_seconds: int


class AttachDatabase(BaseModel, Command[DeliveryStepDetails]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    access: AccessContext
    application_id: UUID
    request: ResourceAttachmentSpec
    idempotency_key: str
    now: datetime

    @model_validator(mode="after")
    def validate_input(self) -> Self:
        if not IDEMPOTENCY.fullmatch(self.idempotency_key):
            raise PlatformRequestError("invalid_idempotency_key", "Idempotency-Key is invalid", 422)
        request = self.request
        if not (
            IDENTIFIER.fullmatch(request.template_id)
            and IDENTIFIER.fullmatch(request.target_id)
            and IDENTIFIER.fullmatch(request.size_id)
            and re.fullmatch(r"[0-9]{1,2}", request.version)
        ):
            raise PlatformRequestError("invalid_resource", "Resource request is invalid", 422)
        if type(request.ttl_seconds) is not int or not 60 <= request.ttl_seconds <= 86400:
            raise PlatformRequestError("invalid_lease", "Resource lifetime is outside policy", 422)
        return self

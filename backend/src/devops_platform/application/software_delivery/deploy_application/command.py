from dataclasses import dataclass
from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from devops_platform.application.shared.errors import PlatformRequestError
from devops_platform.application.software_delivery.shared.models import DeploymentDetails
from devops_platform.application.software_delivery.shared.policy import (
    IDEMPOTENCY,
    IDENTIFIER,
)
from devops_platform.domain.errors import DomainError
from devops_platform.domain.value_objects.access_context import AccessContext
from devops_platform.domain.value_objects.image_digest import ImageDigest
from shared.dispatch import Command


@dataclass(frozen=True)
class DeploymentSpec:
    image_digest: str
    target_id: str = "local"


class DeployApplication(BaseModel, Command[DeploymentDetails]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    access: AccessContext
    application_id: UUID
    request: DeploymentSpec
    idempotency_key: str
    now: datetime

    @model_validator(mode="after")
    def validate_input(self) -> Self:
        if not IDEMPOTENCY.fullmatch(self.idempotency_key):
            raise PlatformRequestError("invalid_idempotency_key", "Idempotency-Key is invalid", 422)
        request = self.request
        try:
            image = ImageDigest(request.image_digest)
        except DomainError as error:
            raise PlatformRequestError(
                "immutable_image_required",
                "Deployment requires an image pinned by SHA-256 digest",
                422,
            ) from error
        if image.is_local_image_id and request.target_id != "local":
            raise PlatformRequestError(
                "immutable_image_required",
                "Bare Docker image IDs are supported only for the local target",
                422,
            )
        if not IDENTIFIER.fullmatch(request.target_id):
            raise PlatformRequestError("invalid_target", "Deployment target is invalid", 422)
        return self

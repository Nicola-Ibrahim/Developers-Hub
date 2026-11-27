import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, PrivateAttr, model_validator

from devops_platform.application.resource_management.submit_database_request.result import (
    AcceptedDatabaseRequest,
)
from devops_platform.application.shared.errors import PlatformRequestError
from devops_platform.domain.errors import DomainError, LeaseViolation
from devops_platform.domain.value_objects.access_context import AccessContext
from devops_platform.domain.value_objects.idempotency_key import IdempotencyKey
from devops_platform.domain.value_objects.resource_name import ResourceName
from shared.dispatch import Command

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_VERSION = re.compile(r"[0-9]{1,2}")


@dataclass(frozen=True)
class DatabaseRequest:
    project_id: UUID
    environment_id: UUID
    display_name: str
    template_id: str
    version: str
    target_id: str
    size_id: str
    ttl_seconds: int


class RequestTemporaryDatabase(BaseModel, Command[AcceptedDatabaseRequest]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    access: AccessContext
    request: DatabaseRequest
    idempotency_key: str
    now: datetime

    _validated_key: IdempotencyKey = PrivateAttr()
    _resource_name: ResourceName = PrivateAttr()

    @property
    def validated_key(self) -> IdempotencyKey:
        return self._validated_key

    @property
    def resource_name(self) -> ResourceName:
        return self._resource_name

    @model_validator(mode="after")
    def _validate(self) -> "RequestTemporaryDatabase":
        request = self.request
        try:
            key = IdempotencyKey(self.idempotency_key)
            name = ResourceName(request.display_name)
        except DomainError as error:
            raise PlatformRequestError(
                "invalid_request", "Invalid request or idempotency key", 422
            ) from error
        if len(request.display_name) > 100:
            raise PlatformRequestError("invalid_request", "Invalid request or idempotency key", 422)

        if not _VERSION.fullmatch(request.version) or not all(
            _IDENTIFIER.fullmatch(value)
            for value in (request.template_id, request.target_id, request.size_id)
        ):
            raise PlatformRequestError("invalid_request", "Invalid catalog selection", 422)
        if isinstance(request.ttl_seconds, bool) or not isinstance(request.ttl_seconds, int):
            raise LeaseViolation("Lease duration must be an integer number of seconds.")
        if request.ttl_seconds <= 0:
            raise LeaseViolation("Lease duration must be positive.")
        if request.ttl_seconds > 86400:
            raise LeaseViolation("Requested lease exceeds the maximum lifetime.")

        self._validated_key = key
        self._resource_name = name
        return self

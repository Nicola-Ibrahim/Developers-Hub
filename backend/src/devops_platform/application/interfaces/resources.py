"""Application contracts grouped by capability."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from devops_platform.application.resource_management.read_models import (
    OperationDetails,
    ResourceDetails,
)
from devops_platform.application.shared.dto import AccessContext
from devops_platform.domain.aggregates.resource_lifecycle import ResourceLifecycle
from devops_platform.domain.entities.operation import AcceptedResourceRequest
from devops_platform.domain.value_objects.idempotency_key import IdempotencyKey

"""Resource lifecycle ports and private worker values."""


@dataclass(frozen=True)
class DatabaseCredentials:
    user: str
    database: str
    password: str = field(repr=False)
    administrator_password: str = field(repr=False)


@dataclass(frozen=True)
class ProvisioningJob:
    operation_id: UUID
    resource_id: UUID
    installation_id: UUID
    generation: int
    claim_token: UUID
    action: str
    cpu_millis: int
    memory_bytes: int
    credentials: DatabaseCredentials = field(repr=False)


@dataclass(frozen=True)
class DatabaseEndpoint:
    host: str
    port: int


@dataclass(frozen=True)
class DeletionObservation:
    absent: bool
    observed_owned_object: bool


class ProviderFailure(Exception):
    def __init__(self, code: str = "provider_unavailable", uncertain: bool = True) -> None:
        super().__init__(code)
        self.code = code
        self.uncertain = uncertain


class LocalDatabaseProvider(Protocol):
    async def provision(self, job: ProvisioningJob) -> DatabaseEndpoint: ...
    async def delete(self, job: ProvisioningJob) -> DeletionObservation: ...
    async def inspect(self, job: ProvisioningJob) -> DatabaseEndpoint | None: ...
    async def discover(self, installation_id: UUID) -> tuple[UUID, ...]: ...


class ResourceCredentialCipher(Protocol):
    def encrypt(self, resource_id: UUID, credentials: DatabaseCredentials) -> bytes: ...
    def decrypt(self, resource_id: UUID, ciphertext: bytes, key_id: str) -> DatabaseCredentials: ...


class ProvisioningQueue(Protocol):
    async def claim(self) -> ProvisioningJob | None: ...
    async def heartbeat(self, job: ProvisioningJob) -> bool: ...
    async def ready(self, job: ProvisioningJob, endpoint: DatabaseEndpoint) -> None: ...
    async def deleted(self, job: ProvisioningJob, observation: DeletionObservation) -> None: ...
    async def failed(self, job: ProvisioningJob, error: ProviderFailure) -> None: ...
    async def sweep(self) -> None: ...
    async def should_execute(self, job: ProvisioningJob) -> bool: ...
    async def reconcile(self, resource_ids: tuple[UUID, ...]) -> None: ...


"""Application contract and projections for the resource aggregate repository."""


@dataclass(frozen=True)
class ResourceSnapshot:
    id: UUID
    project_id: UUID
    environment_id: UUID | None
    owner_id: UUID
    display_name: str
    template_id: str
    target_id: str
    size_id: str
    desired_state: str
    status: str
    revision: int
    created_at: datetime
    expires_at: datetime
    failure_code: str | None


@dataclass(frozen=True)
class ResourceConnectionSecret:
    resource_id: UUID
    host: str
    port: int
    ciphertext: bytes = field(repr=False)
    key_id: str


@dataclass(frozen=True)
class ResourceActivity:
    id: UUID
    actor_id: UUID | None
    resource_id: UUID
    operation_id: UUID
    action: str
    created_at: datetime


class ResourceRepository(Protocol):
    """Resource aggregate persistence used by application use cases and queries."""

    async def replay_request(
        self, access: AccessContext, key: IdempotencyKey, request_hash: str
    ) -> AcceptedResourceRequest | None: ...

    async def accept_database_request(
        self,
        access: AccessContext,
        lifecycle: ResourceLifecycle,
        key: IdempotencyKey,
        request_hash: str,
    ) -> AcceptedResourceRequest: ...

    async def renew(
        self, *, access: AccessContext, resource_id: UUID, revision: int, expiry: datetime
    ) -> ResourceSnapshot: ...

    async def delete(self, *, access: AccessContext, resource_id: UUID) -> UUID: ...

    async def connection(
        self, *, access: AccessContext, resource_id: UUID
    ) -> ResourceConnectionSecret: ...

    async def activity(self, project_id: UUID, limit: int) -> tuple[ResourceActivity, ...]: ...

    async def list_resources(
        self, project_id: UUID, after: UUID | None, limit: int
    ) -> tuple[ResourceDetails, ...]: ...

    async def find_resource(
        self, project_id: UUID, resource_id: UUID
    ) -> ResourceDetails | None: ...

    async def find_operation(
        self, project_id: UUID, operation_id: UUID
    ) -> OperationDetails | None: ...

"""Identity-owned API token persistence contract."""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from identity.domain.aggregates.api_token import ApiTokenAuthenticationDetails
from identity.domain.records import (
    ApiTokenAuditEvent,
    ApiTokenStatus,
    PersonalApiToken,
)


class ApiTokenRepository(ABC):
    """Token queries and writes; transaction completion belongs to the host."""

    @abstractmethod
    async def find_token_credential(self, digest: str) -> ApiTokenAuthenticationDetails | None: ...

    @abstractmethod
    async def record_token_audit(self, event: ApiTokenAuditEvent) -> None: ...

    @abstractmethod
    async def find_api_token(self, token_id: UUID) -> ApiTokenStatus | None:
        """Read the token under a lock held through revocation and its audit write."""
        ...

    @abstractmethod
    async def revoke_api_token(self, token_id: UUID, revoked_at: datetime) -> None: ...

    @abstractmethod
    async def list_personal_tokens(
        self, user_id: UUID, project_id: UUID | None
    ) -> tuple[PersonalApiToken, ...]: ...

    @abstractmethod
    async def create_personal_token(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        name: str,
        digest: str,
        scopes: tuple[str, ...],
        created_at: datetime,
        expires_at: datetime,
    ) -> UUID: ...

    @abstractmethod
    async def rotate_personal_token(
        self,
        *,
        user_id: UUID,
        token_id: UUID,
        digest: str,
        now: datetime,
        allowed_scopes: tuple[str, ...],
    ) -> PersonalApiToken | None: ...

    @abstractmethod
    async def lock_personal_token(
        self, token_id: UUID, *, user_id: UUID | None = None
    ) -> ApiTokenStatus | None: ...

    @abstractmethod
    async def revoke_personal_token(
        self, *, user_id: UUID, token_id: UUID, now: datetime
    ) -> bool: ...

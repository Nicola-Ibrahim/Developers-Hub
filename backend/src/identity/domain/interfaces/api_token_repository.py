"""Identity-owned API token persistence contract."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from identity.domain.aggregates.api_token import ApiTokenAuthenticationDetails
from identity.domain.records import (
    ApiTokenAuditEvent,
    ApiTokenStatus,
    PersonalApiToken,
    ProjectMembershipStatus,
)


class ApiTokenRepository(Protocol):
    """Token queries and writes; transaction completion belongs to the host."""

    async def find_token_credential(self, digest: str) -> ApiTokenAuthenticationDetails | None: ...

    async def require_project_membership(
        self, *, user_name: str, project_name: str
    ) -> ProjectMembershipStatus: ...

    async def insert_api_token(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        digest: str,
        scopes: tuple[str, ...],
        expires_at: datetime,
        created_at: datetime,
        name: str = "Legacy token",
    ) -> UUID: ...

    async def record_token_audit(self, event: ApiTokenAuditEvent) -> None: ...

    async def find_api_token(self, token_id: UUID) -> ApiTokenStatus | None:
        """Read the token under a lock held through revocation and its audit write."""
        ...

    async def revoke_api_token(self, token_id: UUID, revoked_at: datetime) -> None: ...

    async def list_personal_tokens(
        self, user_id: UUID, project_id: UUID | None
    ) -> tuple[PersonalApiToken, ...]: ...

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

    async def rotate_personal_token(
        self,
        *,
        user_id: UUID,
        token_id: UUID,
        digest: str,
        now: datetime,
        allowed_scopes: tuple[str, ...],
    ) -> PersonalApiToken | None: ...

    async def lock_personal_token(self, token_id: UUID) -> ApiTokenStatus | None: ...

    async def revoke_personal_token(
        self, *, user_id: UUID, token_id: UUID, now: datetime
    ) -> bool: ...

"""SQLAlchemy implementation of identity's API token repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.shared.errors import IdentityUnavailable
from identity.domain.aggregates.api_token import ApiTokenAuthenticationDetails
from identity.domain.errors import IdentityValidationError
from identity.domain.interfaces.project_access import IdentityProjectAccess
from identity.domain.records import ApiTokenAuditEvent, ApiTokenStatus, ProjectMembershipStatus
from identity.infra.persistence.models.api_token import ApiAccessTokenRow
from identity.infra.persistence.models.user import InternalUserRow
from shared.infra.persistence.audit import AuditEvent


class SQLAlchemyApiTokenRepository:
    """Identity persistence bound to an operation-scoped session."""

    def __init__(self, session: AsyncSession, project_access: IdentityProjectAccess) -> None:
        self._session = session
        self._project_access = project_access

    async def find_token_credential(self, digest: str) -> ApiTokenAuthenticationDetails | None:
        try:
            return await self._project_access.find_token_credential(digest)
        except SQLAlchemyError as exc:
            raise IdentityUnavailable() from exc

    async def require_project_membership(
        self, *, user_name: str, project_name: str
    ) -> ProjectMembershipStatus:
        try:
            project_id = await self._project_access.lock_named_project(project_name)
            if project_id is None:
                raise IdentityValidationError("Project and current membership are required")
            user = await self._session.scalar(
                select(InternalUserRow).where(InternalUserRow.name == user_name).with_for_update()
            )
            if user is None:
                raise IdentityValidationError(
                    "Active account and current project membership are required"
                )
            if not await self._project_access.lock_project_membership(user.id, project_id):
                raise IdentityValidationError(
                    "Active account and current project membership are required"
                )
            return ProjectMembershipStatus(
                user_id=user.id, project_id=project_id, user_active=user.active
            )
        except SQLAlchemyError as exc:
            raise IdentityUnavailable() from exc

    async def insert_api_token(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        digest: str,
        scopes: tuple[str, ...],
        expires_at: datetime,
        created_at: datetime,
    ) -> UUID:
        try:
            token = ApiAccessTokenRow(
                user_id=user_id,
                project_id=project_id,
                digest=digest,
                scopes=list(scopes),
                created_at=created_at,
                expires_at=expires_at,
                revoked_at=None,
            )
            self._session.add(token)
            await self._session.flush()
            return token.id
        except SQLAlchemyError as exc:
            raise IdentityUnavailable() from exc

    async def record_token_audit(self, event: ApiTokenAuditEvent) -> None:
        try:
            self._session.add(
                AuditEvent(
                    actor_id=event.actor_id,
                    project_id=event.project_id,
                    action=event.action,
                    outcome=event.outcome,
                    request_id=event.request_id,
                )
            )
        except SQLAlchemyError as exc:
            raise IdentityUnavailable() from exc

    async def find_api_token(self, token_id: UUID) -> ApiTokenStatus | None:
        """Lock the token through the revocation decision and its audit write."""
        try:
            token = await self._session.get(
                ApiAccessTokenRow, token_id, with_for_update=True, populate_existing=True
            )
            if token is None:
                return None
            return ApiTokenStatus(token.id, token.user_id, token.project_id, token.revoked_at)
        except SQLAlchemyError as exc:
            raise IdentityUnavailable() from exc

    async def revoke_api_token(self, token_id: UUID, revoked_at: datetime) -> None:
        try:
            token = await self._session.get(ApiAccessTokenRow, token_id)
            if token is not None:
                token.revoked_at = revoked_at
        except SQLAlchemyError as exc:
            raise IdentityUnavailable() from exc

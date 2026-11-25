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
from identity.domain.records import (
    ApiTokenAuditEvent,
    ApiTokenStatus,
    PersonalApiToken,
)
from identity.infra.persistence.models.api_token import ApiAccessTokenRow
from shared.infra.persistence.audit import AuditEvent


class SQLAlchemyApiTokenRepository:
    """Identity persistence bound to an operation-scoped session."""

    def __init__(self, session: AsyncSession, project_access: IdentityProjectAccess) -> None:
        self._session = session
        self._project_access = project_access

    async def find_token_credential(self, digest: str) -> ApiTokenAuthenticationDetails | None:
        try:
            # Acquire the token lock first. The subsequent joined FOR SHARE query also
            # locks the user and membership rows; this aligns token auth with rotation.
            token = await self._session.scalar(
                select(ApiAccessTokenRow)
                .where(ApiAccessTokenRow.digest == digest)
                .with_for_update(read=True, of=ApiAccessTokenRow)
            )
            if token is None:
                return None
            return await self._project_access.find_token_credential(digest)
        except SQLAlchemyError as exc:
            raise IdentityUnavailable() from exc

    async def list_personal_tokens(
        self, user_id: UUID, project_id: UUID | None
    ) -> tuple[PersonalApiToken, ...]:
        query = select(ApiAccessTokenRow).where(ApiAccessTokenRow.user_id == user_id)
        if project_id is not None:
            query = query.where(ApiAccessTokenRow.project_id == project_id)
        rows = (
            await self._session.scalars(query.order_by(ApiAccessTokenRow.created_at.desc()))
        ).all()
        return tuple(
            PersonalApiToken(
                row.id, row.name, row.project_id, tuple(row.scopes), row.expires_at, row.revoked_at
            )
            for row in rows
        )

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
    ) -> UUID:
        try:
            if not await self._project_access.lock_project_membership(user_id, project_id):
                raise IdentityValidationError("Current project membership is required")
            row = ApiAccessTokenRow(
                user_id=user_id,
                project_id=project_id,
                name=name,
                digest=digest,
                scopes=list(scopes),
                created_at=created_at,
                expires_at=expires_at,
                revoked_at=None,
            )
            self._session.add(row)
            await self._session.flush()
            return row.id
        except SQLAlchemyError as exc:
            raise IdentityUnavailable() from exc

    async def rotate_personal_token(
        self,
        *,
        user_id: UUID,
        token_id: UUID,
        digest: str,
        now: datetime,
        allowed_scopes: tuple[str, ...],
    ) -> PersonalApiToken | None:
        try:
            row = await self._session.scalar(
                select(ApiAccessTokenRow)
                .where(ApiAccessTokenRow.id == token_id, ApiAccessTokenRow.user_id == user_id)
                .with_for_update()
            )
            if row is None or row.revoked_at is not None or row.expires_at <= now:
                return None
            if not set(row.scopes) <= set(allowed_scopes):
                return None
            if not await self._project_access.lock_project_membership(user_id, row.project_id):
                return None
            row.revoked_at = now
            replacement = ApiAccessTokenRow(
                user_id=user_id,
                project_id=row.project_id,
                name=row.name,
                digest=digest,
                scopes=list(row.scopes),
                created_at=now,
                expires_at=row.expires_at,
                revoked_at=None,
            )
            self._session.add(replacement)
            await self._session.flush()
            return PersonalApiToken(
                replacement.id,
                replacement.name,
                replacement.project_id,
                tuple(replacement.scopes),
                replacement.expires_at,
                None,
            )
        except SQLAlchemyError as exc:
            raise IdentityUnavailable() from exc

    async def lock_personal_token(self, token_id: UUID) -> ApiTokenStatus | None:
        try:
            row = await self._session.scalar(
                select(ApiAccessTokenRow)
                .where(ApiAccessTokenRow.id == token_id)
                .with_for_update(of=ApiAccessTokenRow)
            )
            if row is None:
                return None
            return ApiTokenStatus(row.id, row.user_id, row.project_id, row.revoked_at)
        except SQLAlchemyError as exc:
            raise IdentityUnavailable() from exc

    async def revoke_personal_token(self, *, user_id: UUID, token_id: UUID, now: datetime) -> bool:
        try:
            row = await self._session.scalar(
                select(ApiAccessTokenRow)
                .where(ApiAccessTokenRow.id == token_id, ApiAccessTokenRow.user_id == user_id)
                .with_for_update()
            )
            if row is None:
                return False
            if row.revoked_at is None:
                row.revoked_at = now
                await self.record_token_audit(
                    ApiTokenAuditEvent(
                        user_id, row.project_id, "token_revoked", "succeeded", token_id
                    )
                )
            return True
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

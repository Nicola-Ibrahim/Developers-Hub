"""SQLAlchemy adapter for the browser session revocation write contract."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.aggregates.session import Session
from identity.domain.interfaces.session_revocation_repository import SessionRevocationRepository
from identity.domain.value_objects.session_expiry import SessionExpiry
from identity.infra.persistence.models.activity import IdentityActivityRow
from identity.infra.persistence.models.session import BrowserSessionRow


class SQLAlchemySessionRevocationRepository(SessionRevocationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._locked_rows: dict[UUID, BrowserSessionRow] = {}

    async def load_for_revocation(self, user_id: UUID, session_id: UUID) -> Session | None:
        row = await self._session.scalar(
            select(BrowserSessionRow)
            .where(BrowserSessionRow.user_id == user_id, BrowserSessionRow.id == session_id)
            .with_for_update()
        )
        if row is None:
            return None

        self._locked_rows[row.id] = row
        return self._domain_session(row)

    @staticmethod
    def _domain_session(row: BrowserSessionRow) -> Session:
        return Session(
            row.id,
            row.user_id,
            row.created_at,
            row.last_seen_at,
            SessionExpiry(row.idle_expires_at, row.absolute_expires_at),
            row.revoked_at,
            row.credential_version,
        )

    async def save_revocation(self, session: Session) -> None:
        row = self._locked_rows.get(session.id)
        if row is None or row.user_id != session.user_id:
            raise ValueError("Session must be loaded for revocation by this repository.")
        if row.revoked_at is not None or session.revoked_at is None:
            raise ValueError("A revocation save must represent the first revocation transition.")
        row.revoked_at = session.revoked_at
        self._session.add(
            IdentityActivityRow(
                actor_id=session.user_id,
                subject_id=session.user_id,
                project_id=row.selected_project_id,
                action="browser_session_revoked",
                outcome="succeeded",
                created_at=session.revoked_at,
            )
        )

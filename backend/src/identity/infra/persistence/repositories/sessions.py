"""SQLAlchemy repository for browser session state."""

import hmac
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.shared.principal import principal_for_project
from identity.domain.aggregates.session import Session
from identity.domain.interfaces.project_access import IdentityProjectAccess
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository
from identity.domain.records import MembershipDetails, SessionPrincipal
from identity.domain.value_objects.session_expiry import SessionExpiry
from identity.infra.persistence.models.activity import IdentityActivityRow
from identity.infra.persistence.models.session import BrowserSessionRow

_IDLE_WINDOW = timedelta(minutes=30)


class SQLAlchemySessionRepository(SessionRepository):
    """Persist session aggregate operations using one caller-owned SQL session."""

    def __init__(
        self,
        session: AsyncSession,
        users: UserRepository,
        project_access: IdentityProjectAccess,
    ) -> None:
        self._session = session
        self._users = users
        self._project_access = project_access
        self._locked_rows: dict[UUID, BrowserSessionRow] = {}

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

    async def _memberships(self, user_id: UUID) -> tuple[MembershipDetails, ...]:
        rows = await self._project_access.project_memberships(user_id)
        return tuple(MembershipDetails(project_id, name, role) for project_id, name, role in rows)

    async def create_login_session(
        self,
        *,
        user_id: UUID,
        user_name: str,
        credential_version: int,
        token_digest: str,
        csrf_digest: str,
        now: datetime,
    ) -> tuple[SessionPrincipal, UUID, datetime]:
        expires_at = now + timedelta(hours=8)
        row = BrowserSessionRow(
            user_id=user_id,
            token_digest=token_digest,
            csrf_digest=csrf_digest,
            credential_version=credential_version,
            created_at=now,
            last_seen_at=now,
            idle_expires_at=now + _IDLE_WINDOW,
            absolute_expires_at=expires_at,
        )
        self._session.add(row)
        await self._session.flush()
        await self._record_activity(user_id, user_id, None, "browser_login", "succeeded", now)
        memberships = await self._memberships(user_id)
        principal = principal_for_project(
            user_id=user_id,
            user_name=user_name,
            session_id=row.id,
            memberships=memberships,
            project_id=None,
            csrf_token="",
        )
        return principal, row.id, expires_at

    async def authenticate_session(
        self,
        *,
        token_digest: str,
        project_id: UUID | None,
        now: datetime,
    ) -> tuple[SessionPrincipal, str] | None:
        row = await self._session.scalar(
            select(BrowserSessionRow).where(BrowserSessionRow.token_digest == token_digest)
        )
        if row is None:
            return None
        user = await self._users.load_session_account(row.user_id)
        if (
            user is None
            or not self._domain_session(row).accepts(
                now=now,
                user_active=user.active,
                credential_version=user.credential_version,
            )
            or row.credential_version != user.credential_version
        ):
            return None
        memberships = await self._memberships(user.user_id)
        selected_project_id = project_id if project_id is not None else row.selected_project_id
        if selected_project_id is not None and not any(
            item.project_id == selected_project_id for item in memberships
        ):
            return None
        if now - row.last_seen_at >= timedelta(minutes=5):
            row.last_seen_at = now
            row.idle_expires_at = min(now + _IDLE_WINDOW, row.absolute_expires_at)
        principal = principal_for_project(
            user_id=user.user_id,
            user_name=user.user_name,
            session_id=row.id,
            memberships=memberships,
            project_id=selected_project_id,
            csrf_token="",
        )
        return principal, row.csrf_digest

    async def authorize_browser_operation(
        self,
        token_digest: str,
        project_id: UUID | None,
        now: datetime,
        lock_for_mutation: bool = False,
    ) -> SessionPrincipal | None:
        snapshot = await self._session.scalar(
            select(BrowserSessionRow).where(BrowserSessionRow.token_digest == token_digest)
        )
        if snapshot is None:
            return None
        selected = project_id if project_id is not None else snapshot.selected_project_id
        project_ids = await self._project_access.lock_user_project_access(
            snapshot.user_id, (selected,) if selected is not None else ()
        )
        if project_ids is None or (selected is not None and selected not in project_ids):
            return None
        user = await self._users.load_session_account(
            snapshot.user_id,
            lock_for_update=True,
            shared_lock=not lock_for_mutation,
        )
        row = await self._session.scalar(
            select(BrowserSessionRow)
            .where(
                BrowserSessionRow.id == snapshot.id,
                BrowserSessionRow.token_digest == token_digest,
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if (
            row is None
            or row.user_id != snapshot.user_id
            or user is None
            or not user.active
            or user.credential_version != row.credential_version
        ):
            return None
        current_selected = project_id if project_id is not None else row.selected_project_id
        if current_selected != selected:
            return None
        if not self._domain_session(row).accepts(
            now=now,
            user_active=user.active,
            credential_version=user.credential_version,
        ):
            return None
        if selected is not None and not await self._project_access.project_membership_role(
            user.user_id, selected
        ):
            return None
        memberships = await self._memberships(user.user_id)
        if now - row.last_seen_at >= timedelta(minutes=5):
            row.last_seen_at = now
            row.idle_expires_at = min(now + _IDLE_WINDOW, row.absolute_expires_at)
        return principal_for_project(
            user_id=user.user_id,
            user_name=user.user_name,
            session_id=row.id,
            memberships=memberships,
            project_id=selected,
            csrf_token="",
        )

    async def select_project(
        self,
        *,
        token_digest: str,
        project_id: UUID,
        now: datetime,
    ) -> SessionPrincipal | None:
        snapshot = await self._session.scalar(
            select(BrowserSessionRow).where(BrowserSessionRow.token_digest == token_digest)
        )
        if snapshot is None:
            return None
        if not await self._project_access.project_membership_role(snapshot.user_id, project_id):
            return None
        project_ids = await self._project_access.lock_user_project_access(
            snapshot.user_id, (project_id,)
        )
        if project_ids is None or project_id not in project_ids:
            return None
        user = await self._users.load_session_account(snapshot.user_id, lock_for_update=True)
        row = await self._session.scalar(
            select(BrowserSessionRow)
            .where(
                BrowserSessionRow.id == snapshot.id,
                BrowserSessionRow.token_digest == token_digest,
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if (
            row is None
            or row.user_id != snapshot.user_id
            or user is None
            or not self._domain_session(row).accepts(
                now=now,
                user_active=user.active,
                credential_version=user.credential_version,
            )
            or row.credential_version != user.credential_version
        ):
            return None
        if not await self._project_access.project_membership_role(user.user_id, project_id):
            return None
        memberships = await self._memberships(user.user_id)
        row.selected_project_id = project_id
        row.last_seen_at = now
        row.idle_expires_at = min(now + _IDLE_WINDOW, row.absolute_expires_at)
        return principal_for_project(
            user_id=user.user_id,
            user_name=user.user_name,
            session_id=row.id,
            memberships=memberships,
            project_id=project_id,
            csrf_token="",
        )

    async def rotate_csrf(self, token_digest: str, csrf_digest: str, now: datetime) -> bool:
        row = await self._session.scalar(
            select(BrowserSessionRow)
            .where(BrowserSessionRow.token_digest == token_digest)
            .with_for_update()
        )
        if row is None or row.revoked_at is not None or row.absolute_expires_at <= now:
            return False
        row.csrf_digest = csrf_digest
        return True

    async def validate_csrf(self, token_digest: str, csrf_digest: str) -> bool:
        stored = await self._session.scalar(
            select(BrowserSessionRow.csrf_digest).where(
                BrowserSessionRow.token_digest == token_digest,
                BrowserSessionRow.revoked_at.is_(None),
            )
        )
        return stored is not None and hmac.compare_digest(stored, csrf_digest)

    async def logout(self, token_digest: str, now: datetime) -> None:
        row = await self._session.scalar(
            select(BrowserSessionRow)
            .where(BrowserSessionRow.token_digest == token_digest)
            .with_for_update()
        )
        if row is not None and row.revoked_at is None:
            row.revoked_at = now
            await self._record_activity(
                row.user_id,
                row.user_id,
                row.selected_project_id,
                "browser_logout",
                "succeeded",
                now,
            )

    async def logout_all(self, user_id: UUID, now: datetime) -> int:
        result = await self._session.execute(
            update(BrowserSessionRow)
            .where(BrowserSessionRow.user_id == user_id, BrowserSessionRow.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        count = int(getattr(result, "rowcount", 0) or 0)
        await self._record_activity(
            user_id, user_id, None, "all_browser_sessions_revoked", "succeeded", now
        )
        return count

    async def revoke_user_sessions(self, user_id: UUID, now: datetime) -> None:
        await self._session.execute(
            update(BrowserSessionRow)
            .where(BrowserSessionRow.user_id == user_id, BrowserSessionRow.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def list_sessions(
        self, user_id: UUID, current_session_id: UUID, now: datetime
    ) -> tuple[Session, ...]:
        rows = (
            await self._session.scalars(
                select(BrowserSessionRow)
                .where(
                    BrowserSessionRow.user_id == user_id,
                    BrowserSessionRow.revoked_at.is_(None),
                    BrowserSessionRow.idle_expires_at > now,
                    BrowserSessionRow.absolute_expires_at > now,
                )
                .order_by(BrowserSessionRow.created_at.desc())
            )
        ).all()
        return tuple(self._domain_session(row) for row in rows)

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

    async def save_revocation(self, session: Session) -> None:
        row = self._locked_rows.get(session.id)
        if row is None or row.user_id != session.user_id:
            raise ValueError("Session must be loaded for revocation by this repository.")
        if row.revoked_at is not None or session.revoked_at is None:
            raise ValueError("A revocation save must represent the first revocation transition.")
        row.revoked_at = session.revoked_at
        await self._record_activity(
            session.user_id,
            session.user_id,
            row.selected_project_id,
            "browser_session_revoked",
            "succeeded",
            session.revoked_at,
        )

    async def _record_activity(
        self,
        actor_id: UUID | None,
        subject_id: UUID | None,
        project_id: UUID | None,
        action: str,
        outcome: str,
        now: datetime,
    ) -> None:
        self._session.add(
            IdentityActivityRow(
                actor_id=actor_id,
                subject_id=subject_id,
                project_id=project_id,
                action=action,
                outcome=outcome,
                created_at=now,
            )
        )

    async def record_project_access_activity(
        self,
        actor_id: UUID | None,
        subject_id: UUID,
        project_id: UUID | None,
        action: str,
        outcome: str,
        now: datetime,
    ) -> None:
        await self._record_activity(actor_id, subject_id, project_id, action, outcome, now)

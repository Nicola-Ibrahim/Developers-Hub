"""SQLAlchemy adapter for browser credentials, sessions and account administration."""

import hmac
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from devops_platform.infra.persistence.repositories.project_access import (
    lock_user_project_access,
    project_membership_role,
    project_memberships,
)
from identity.application.shared.principal import principal_for_project
from identity.domain.aggregates.session import Session
from identity.domain.errors import IdentityValidationError
from identity.domain.interfaces.password_setup_repository import PasswordSetupRepository
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository
from identity.domain.records import (
    AccountCredentials,
    MembershipDetails,
    SessionPrincipal,
)
from identity.domain.value_objects.session_expiry import SessionExpiry
from identity.infra.persistence.models.activity import IdentityActivityRow
from identity.infra.persistence.models.session import (
    BrowserLoginThrottleRow,
    BrowserSessionRow,
)
from identity.infra.persistence.models.user import (
    InternalUserRow,
    PasswordSetupRow,
)

_THROTTLE_WINDOW = timedelta(minutes=15)
_MAX_FAILURES = 6
_LOCK_TIME = timedelta(minutes=15)
_IDLE_WINDOW = timedelta(minutes=30)


class ProjectAccessRulesPort(Protocol):
    async def lock_account_projects(self, user_id: UUID) -> tuple[UUID, ...]: ...

    async def deactivation_conflict(
        self, user_id: UUID, locked_project_ids: tuple[UUID, ...]
    ) -> str | None: ...

    async def demote_admin_memberships(self, user_id: UUID) -> None: ...


class SQLAlchemyIdentityRepository(
    UserRepository,
    SessionRepository,
    PasswordSetupRepository,
):
    def __init__(
        self,
        session: AsyncSession,
        project_access_rules: ProjectAccessRulesPort | None = None,
    ) -> None:
        self._session = session
        self._project_access_rules = project_access_rules

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
        rows = await project_memberships(self._session, user_id)
        return tuple(MembershipDetails(project_id, name, role) for project_id, name, role in rows)

    async def find_login_account(self, user_name: str) -> AccountCredentials | None:
        user = await self._session.scalar(
            select(InternalUserRow).where(InternalUserRow.name == user_name)
        )
        if user is None or user.password_hash is None:
            return None
        return AccountCredentials(
            user_id=user.id,
            user_name=user.name,
            password_hash=user.password_hash,
            credential_version=user.credential_version,
            active=user.active,
            memberships=await self._memberships(user.id),
        )

    async def complete_login(
        self,
        *,
        user_name: str,
        username_digest: str,
        expected_version: int | None,
        accepted: bool,
        token_digest: str,
        csrf_digest: str,
        now: datetime,
    ) -> tuple[SessionPrincipal, UUID, datetime] | None:
        user = await self._session.scalar(
            select(InternalUserRow).where(InternalUserRow.name == user_name).with_for_update()
        )
        # Do not create an unbounded persistent bucket for arbitrary unknown names.
        if user is None:
            return None
        await self._session.execute(
            insert(BrowserLoginThrottleRow)
            .values(username_digest=username_digest, failures=0, window_started_at=now)
            .on_conflict_do_nothing(index_elements=[BrowserLoginThrottleRow.username_digest])
        )
        throttle = await self._session.scalar(
            select(BrowserLoginThrottleRow)
            .where(BrowserLoginThrottleRow.username_digest == username_digest)
            .with_for_update()
        )
        assert throttle is not None
        locked = throttle.locked_until is not None and throttle.locked_until > now
        if locked:
            return None
        if not accepted or not user.active or user.password_hash is None:
            if throttle.window_started_at + _THROTTLE_WINDOW <= now:
                throttle.failures = 0
                throttle.window_started_at = now
                throttle.locked_until = None
            throttle.failures += 1
            if throttle.failures >= _MAX_FAILURES:
                throttle.locked_until = now + _LOCK_TIME
            await self._record_activity(None, user.id, None, "login_rejected", "failed", now)
            return None
        if user.credential_version != expected_version:
            return None
        throttle.failures = 0
        throttle.window_started_at = now
        throttle.locked_until = None
        idle_expires = now + _IDLE_WINDOW
        absolute_expires = now + timedelta(hours=8)
        session = BrowserSessionRow(
            user_id=user.id,
            token_digest=token_digest,
            csrf_digest=csrf_digest,
            credential_version=user.credential_version,
            created_at=now,
            last_seen_at=now,
            idle_expires_at=idle_expires,
            absolute_expires_at=absolute_expires,
        )
        self._session.add(session)
        await self._session.flush()
        await self._record_activity(user.id, user.id, None, "browser_login", "succeeded", now)
        memberships = await self._memberships(user.id)
        principal = principal_for_project(
            user_id=user.id,
            user_name=user.name,
            session_id=session.id,
            memberships=memberships,
            project_id=None,
            csrf_token="",
        )
        return principal, session.id, absolute_expires

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
        user = await self._session.get(InternalUserRow, row.user_id)
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
        memberships = await self._memberships(user.id)
        selected_project_id = project_id if project_id is not None else row.selected_project_id
        if selected_project_id is not None and not any(
            item.project_id == selected_project_id for item in memberships
        ):
            return None
        if now - row.last_seen_at >= timedelta(minutes=5):
            row.last_seen_at = now
            row.idle_expires_at = min(now + _IDLE_WINDOW, row.absolute_expires_at)
        principal = principal_for_project(
            user_id=user.id,
            user_name=user.name,
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
        # Discover the lock keys without taking a lock. Shared operations then use
        # project -> user -> session, matching membership and account administration.
        snapshot = await self._session.scalar(
            select(BrowserSessionRow).where(BrowserSessionRow.token_digest == token_digest)
        )
        if snapshot is None:
            return None
        selected = project_id if project_id is not None else snapshot.selected_project_id
        project_ids = await lock_user_project_access(
            self._session, snapshot.user_id, (selected,) if selected is not None else ()
        )
        if project_ids is None or (selected is not None and selected not in project_ids):
            return None
        user_statement = select(InternalUserRow).where(InternalUserRow.id == snapshot.user_id)
        user_statement = (
            user_statement.with_for_update()
            if lock_for_mutation
            else user_statement.with_for_update(read=True)
        )
        user = await self._session.scalar(user_statement)
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
        # The selected project may have changed while acquiring locks. Do not use
        # a lock acquired for the previous project to authorize the new selection.
        if current_selected != selected:
            return None
        if not self._domain_session(row).accepts(
            now=now,
            user_active=user.active,
            credential_version=user.credential_version,
        ):
            return None
        if selected is not None:
            role = await project_membership_role(self._session, user.id, selected)
            if role is None:
                return None
        memberships = await self._memberships(user.id)
        if now - row.last_seen_at >= timedelta(minutes=5):
            row.last_seen_at = now
            row.idle_expires_at = min(now + _IDLE_WINDOW, row.absolute_expires_at)
        return principal_for_project(
            user_id=user.id,
            user_name=user.name,
            session_id=row.id,
            memberships=memberships,
            project_id=selected,
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
        if not await project_membership_role(self._session, snapshot.user_id, project_id):
            return None
        project_ids = await lock_user_project_access(self._session, snapshot.user_id, (project_id,))
        if project_ids is None or project_id not in project_ids:
            return None
        user = await self._session.scalar(
            select(InternalUserRow).where(InternalUserRow.id == snapshot.user_id).with_for_update()
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
            or not self._domain_session(row).accepts(
                now=now,
                user_active=user.active,
                credential_version=user.credential_version,
            )
            or row.credential_version != user.credential_version
        ):
            return None
        role = await project_membership_role(self._session, user.id, project_id)
        if role is None:
            return None
        memberships = await self._memberships(user.id)
        row.selected_project_id = project_id
        row.last_seen_at = now
        row.idle_expires_at = min(now + _IDLE_WINDOW, row.absolute_expires_at)
        return principal_for_project(
            user_id=user.id,
            user_name=user.name,
            session_id=row.id,
            memberships=memberships,
            project_id=project_id,
            csrf_token="",
        )

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
        return tuple(
            Session(
                row.id,
                row.user_id,
                row.created_at,
                row.last_seen_at,
                SessionExpiry(row.idle_expires_at, row.absolute_expires_at),
                row.revoked_at,
                row.credential_version,
            )
            for row in rows
        )

    async def change_password(
        self,
        *,
        user_id: UUID,
        expected_version: int,
        password_hash: str,
        now: datetime,
    ) -> bool:
        user = await self._session.scalar(
            select(InternalUserRow).where(InternalUserRow.id == user_id).with_for_update()
        )
        if user is None or not user.active or user.credential_version != expected_version:
            return False
        user.password_hash = password_hash
        user.credential_version += 1
        await self._invalidate_password_setups(user_id, now)
        await self._session.execute(
            update(BrowserSessionRow)
            .where(BrowserSessionRow.user_id == user_id, BrowserSessionRow.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await self._record_activity(user_id, user_id, None, "password_changed", "succeeded", now)
        return True

    async def create_user(
        self, user_name: str, password_hash: str, actor_id: UUID | None, now: datetime
    ) -> UUID:
        user = InternalUserRow(
            name=user_name, active=True, password_hash=password_hash, created_at=now
        )
        self._session.add(user)
        await self._session.flush()
        await self._record_activity(actor_id, user.id, None, "user_created", "succeeded", now)
        return user.id

    async def set_user_active(
        self,
        *,
        actor_id: UUID,
        user_id: UUID,
        active: bool,
        now: datetime,
    ) -> None:
        project_ids: tuple[UUID, ...] = ()
        if not active:
            assert self._project_access_rules is not None
            project_ids = await self._project_access_rules.lock_account_projects(user_id)
        user = await self._session.scalar(
            select(InternalUserRow).where(InternalUserRow.id == user_id).with_for_update()
        )
        if user is None:
            raise IdentityValidationError("User does not exist")
        if user.active == active:
            return
        if not active:
            assert self._project_access_rules is not None
            conflict = await self._project_access_rules.deactivation_conflict(user_id, project_ids)
            if conflict is not None:
                raise IdentityValidationError(conflict)
        user.active = active
        user.credential_version += 1
        await self._invalidate_password_setups(user_id, now)
        if not active:
            await self._session.execute(
                update(BrowserSessionRow)
                .where(BrowserSessionRow.user_id == user_id, BrowserSessionRow.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            assert self._project_access_rules is not None
            await self._project_access_rules.demote_admin_memberships(user_id)
        await self._record_activity(
            actor_id, user_id, None, "user_enabled" if active else "user_disabled", "succeeded", now
        )

    async def issue_password_setup(
        self,
        *,
        user_id: UUID,
        digest: str,
        expires_at: datetime,
        actor_id: UUID,
        now: datetime,
    ) -> None:
        user = await self._session.get(InternalUserRow, user_id, with_for_update=True)
        if user is None or not user.active:
            raise IdentityValidationError("User does not exist or is disabled")
        await self._invalidate_password_setups(user_id, now)
        self._session.add(
            PasswordSetupRow(user_id=user_id, digest=digest, expires_at=expires_at, created_at=now)
        )
        await self._record_activity(
            actor_id, user_id, None, "password_setup_issued", "succeeded", now
        )

    async def consume_password_setup(
        self, *, digest: str, password_hash: str, now: datetime
    ) -> bool:
        # Discover the account without locking the setup row. All writers lock the
        # account first, then re-read setup state after acquiring that lock.
        user_id = await self._session.scalar(
            select(PasswordSetupRow.user_id).where(PasswordSetupRow.digest == digest)
        )
        if user_id is None:
            return False
        user = await self._session.get(InternalUserRow, user_id, with_for_update=True)
        if user is None or not user.active:
            return False
        setup = await self._session.scalar(
            select(PasswordSetupRow).where(
                PasswordSetupRow.digest == digest, PasswordSetupRow.user_id == user_id
            )
        )
        if setup is None or setup.consumed_at is not None or setup.expires_at <= now:
            return False
        await self._invalidate_password_setups(user_id, now)
        user.password_hash = password_hash
        user.credential_version += 1
        await self._session.execute(
            update(BrowserSessionRow)
            .where(BrowserSessionRow.user_id == user.id, BrowserSessionRow.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await self._record_activity(
            user.id, user.id, None, "password_setup_consumed", "succeeded", now
        )
        return True

    async def _invalidate_password_setups(self, user_id: UUID, now: datetime) -> None:
        await self._session.execute(
            update(PasswordSetupRow)
            .where(PasswordSetupRow.user_id == user_id, PasswordSetupRow.consumed_at.is_(None))
            .values(consumed_at=now)
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

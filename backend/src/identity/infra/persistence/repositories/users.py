"""SQLAlchemy repository for Identity user and password setup state."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.errors import IdentityValidationError
from identity.domain.interfaces.project_access import IdentityProjectAccess
from identity.domain.interfaces.user_repository import UserRepository
from identity.domain.records import (
    AccountCredentials,
    AccountProfile,
    AccountSessionDetails,
    SecurityActivity,
)
from identity.infra.persistence.models.activity import IdentityActivityRow
from identity.infra.persistence.models.session import LoginThrottleRow
from identity.infra.persistence.models.user import InternalUserRow, PasswordSetupRow
from shared.infra.persistence.audit import AuditEvent

_THROTTLE_WINDOW = timedelta(minutes=15)
_MAX_FAILURES = 6
_LOCK_TIME = timedelta(minutes=15)


class SQLAlchemyUserRepository(UserRepository):
    """Persist user lifecycle operations on the caller-owned SQL transaction."""

    def __init__(self, session: AsyncSession, project_access: IdentityProjectAccess) -> None:
        self._session = session
        self._project_access = project_access

    async def load_profile(self, user_id: UUID) -> AccountProfile | None:
        user = await self._session.get(InternalUserRow, user_id)
        if user is None:
            return None
        return AccountProfile(user.id, user.name, user.display_name)

    async def update_profile(
        self, *, user_id: UUID, display_name: str | None, now: datetime
    ) -> AccountProfile | None:
        user = await self._session.scalar(
            select(InternalUserRow).where(InternalUserRow.id == user_id).with_for_update()
        )
        if user is None or not user.active:
            return None
        user.display_name = display_name
        await self._record_activity(user_id, user_id, None, "profile_updated", "succeeded", now)
        await self._session.flush()
        return AccountProfile(user.id, user.name, user.display_name)

    async def list_security_history(
        self, user_id: UUID, *, limit: int
    ) -> tuple[SecurityActivity, ...]:
        identity_rows = (
            await self._session.execute(
                select(
                    IdentityActivityRow.id,
                    IdentityActivityRow.action,
                    IdentityActivityRow.outcome,
                    IdentityActivityRow.created_at,
                )
                .where(IdentityActivityRow.subject_id == user_id)
                .order_by(IdentityActivityRow.created_at.desc(), IdentityActivityRow.id.desc())
                .limit(limit)
            )
        ).all()
        token_rows = (
            await self._session.execute(
                select(AuditEvent.id, AuditEvent.action, AuditEvent.outcome, AuditEvent.created_at)
                .where(
                    AuditEvent.actor_id == user_id,
                    AuditEvent.action.in_(("token_issued", "token_revoked", "token_rotated")),
                )
                .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
                .limit(limit)
            )
        ).all()
        activities = [SecurityActivity(*row) for row in (*identity_rows, *token_rows)]
        activities.sort(key=lambda item: (item.created_at, item.id.hex), reverse=True)
        return tuple(activities[:limit])

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
        )

    async def record_login_attempt(
        self,
        *,
        user_name: str,
        username_digest: str,
        expected_version: int | None,
        accepted: bool,
        now: datetime,
        replacement_password_hash: str | None = None,
    ) -> tuple[UUID, str, int] | None:
        user = await self._session.scalar(
            select(InternalUserRow).where(InternalUserRow.name == user_name).with_for_update()
        )
        if user is None:
            return None
        await self._session.execute(
            insert(LoginThrottleRow)
            .values(username_digest=username_digest, failures=0, window_started_at=now)
            .on_conflict_do_nothing(index_elements=[LoginThrottleRow.username_digest])
        )
        throttle = await self._session.scalar(
            select(LoginThrottleRow)
            .where(LoginThrottleRow.username_digest == username_digest)
            .with_for_update()
        )
        assert throttle is not None
        if throttle.locked_until is not None and throttle.locked_until > now:
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
        if replacement_password_hash is not None:
            user.password_hash = replacement_password_hash
        throttle.failures = 0
        throttle.window_started_at = now
        throttle.locked_until = None
        return user.id, user.name, user.credential_version

    async def load_session_account(
        self, user_id: UUID, *, lock_for_update: bool = False, shared_lock: bool = False
    ) -> AccountSessionDetails | None:
        statement = select(InternalUserRow).where(InternalUserRow.id == user_id)
        if lock_for_update:
            statement = statement.with_for_update(read=shared_lock)
        user = await self._session.scalar(statement)
        if user is None:
            return None
        return AccountSessionDetails(user.id, user.name, user.active, user.credential_version)

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
    ) -> bool:
        project_ids: tuple[UUID, ...] = ()
        if not active:
            project_ids = await self._project_access.lock_account_projects(user_id)
        user = await self._session.scalar(
            select(InternalUserRow).where(InternalUserRow.id == user_id).with_for_update()
        )
        if user is None:
            raise IdentityValidationError("User does not exist")
        if user.active == active:
            return False
        if not active:
            conflict = await self._project_access.deactivation_conflict(user_id, project_ids)
            if conflict is not None:
                raise IdentityValidationError(conflict)
        user.active = active
        user.credential_version += 1
        await self._invalidate_password_setups(user_id, now)
        if not active:
            await self._project_access.demote_admin_memberships(user_id)
        await self._record_activity(
            actor_id, user_id, None, "user_enabled" if active else "user_disabled", "succeeded", now
        )
        return True

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
    ) -> UUID | None:
        user_id = await self._session.scalar(
            select(PasswordSetupRow.user_id).where(PasswordSetupRow.digest == digest)
        )
        if user_id is None:
            return None
        user = await self._session.get(InternalUserRow, user_id, with_for_update=True)
        if user is None or not user.active:
            return None
        setup = await self._session.scalar(
            select(PasswordSetupRow).where(
                PasswordSetupRow.digest == digest, PasswordSetupRow.user_id == user_id
            )
        )
        if setup is None or setup.consumed_at is not None or setup.expires_at <= now:
            return None
        await self._invalidate_password_setups(user_id, now)
        user.password_hash = password_hash
        user.credential_version += 1
        await self._record_activity(
            user.id, user.id, None, "password_setup_consumed", "succeeded", now
        )
        return user.id

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

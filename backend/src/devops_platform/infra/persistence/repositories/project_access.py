"""Project access writes and member projections on a caller-owned transaction.

The user ORM row, audit callback, and error factories are supplied by Identity at
composition time. Identity still owns account records and audit semantics; this
adapter owns project membership SQL and uses the existing session and rule query.
"""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from devops_platform.domain.aggregates.project_access import ProjectAccess
from devops_platform.infra.persistence.models.project_access import ProjectMembershipRow, ProjectRow
from identity.infra.persistence.models.user import InternalUserRow

AuditActivity = Callable[[UUID | None, UUID, UUID | None, str, str, datetime], Awaitable[None]]
ValidationErrorFactory = Callable[[str], Exception]
AuthorizationErrorFactory = Callable[[], Exception]


class SQLAlchemyProjectAccessRules:
    """Queries and updates enforcing project membership invariants."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def active_admin_count(self, project_id: UUID) -> int:
        count = await self._session.scalar(
            select(func.count())
            .select_from(ProjectMembershipRow)
            .join(InternalUserRow, InternalUserRow.id == ProjectMembershipRow.user_id)
            .where(
                ProjectMembershipRow.project_id == project_id,
                ProjectMembershipRow.role == "admin",
                InternalUserRow.active.is_(True),
            )
        )
        return int(count or 0)

    async def retains_active_admin(self, project_id: UUID) -> bool:
        return ProjectAccess(await self.active_admin_count(project_id)).may_remove_active_admin()

    async def demote_admin_memberships(self, user_id: UUID) -> None:
        await self._session.execute(
            update(ProjectMembershipRow)
            .where(ProjectMembershipRow.user_id == user_id, ProjectMembershipRow.role == "admin")
            .values(role="developer")
        )


class SQLAlchemyProjectAccessRepository:
    def __init__(
        self,
        session: AsyncSession,
        rules: SQLAlchemyProjectAccessRules,
        user_row: type[Any],
        record_activity: AuditActivity,
        validation_error: ValidationErrorFactory,
        authorization_error: AuthorizationErrorFactory,
    ) -> None:
        self._session = session
        self._rules = rules
        self._user = user_row
        self._record_activity = record_activity
        self._validation_error = validation_error
        self._authorization_error = authorization_error

    async def set_membership(
        self,
        *,
        actor_id: UUID,
        user_id: UUID,
        project_id: UUID,
        role: str | None,
        now: datetime,
    ) -> None:
        if role not in {None, "developer", "admin"}:
            raise self._validation_error("Unsupported project role")
        project_exists = await self.lock_project_membership_admin_scope(project_id)
        target = await self._session.scalar(
            select(self._user).where(self._user.id == user_id).with_for_update(read=True)
        )
        if not project_exists or target is None or not target.active:
            raise self._validation_error("Active user and project are required")
        actor_role = await self._session.scalar(
            select(ProjectMembershipRow.role).where(
                ProjectMembershipRow.user_id == actor_id,
                ProjectMembershipRow.project_id == project_id,
            )
        )
        if actor_role != "admin":
            raise self._authorization_error()
        if actor_id == user_id and role in {None, "developer"}:
            raise self._validation_error("Ask another project administrator to change your role")
        row = await self._session.get(
            ProjectMembershipRow, (user_id, project_id), with_for_update=True
        )
        if role in {None, "developer"} and row is not None and row.role == "admin":
            if not await self._rules.retains_active_admin(project_id):
                raise self._validation_error("A project must retain at least one administrator")
        if role is None:
            if row is not None:
                await self._session.delete(row)
        elif row is None:
            self._session.add(
                ProjectMembershipRow(user_id=user_id, project_id=project_id, role=role)
            )
        else:
            row.role = role
        await self._record_activity(
            actor_id, user_id, project_id, "membership_changed", "succeeded", now
        )

    async def lock_project_membership_admin_scope(self, project_id: UUID) -> bool:
        project = await self._session.scalar(
            select(ProjectRow).where(ProjectRow.id == project_id).with_for_update()
        )
        return project is not None

    async def bootstrap_first_project_admin(
        self, *, user_id: UUID, project_id: UUID, now: datetime
    ) -> None:
        project = await self._session.scalar(
            select(ProjectRow).where(ProjectRow.id == project_id).with_for_update()
        )
        user = await self._session.scalar(
            select(self._user).where(self._user.id == user_id).with_for_update()
        )
        if project is None or user is None or not user.active:
            raise self._validation_error("Active user and project are required")
        admin_count = await self._session.scalar(
            select(func.count())
            .select_from(ProjectMembershipRow)
            .where(
                ProjectMembershipRow.project_id == project_id,
                ProjectMembershipRow.role == "admin",
            )
        )
        if admin_count:
            raise self._validation_error("Project already has an administrator")
        membership = await self._session.get(ProjectMembershipRow, (user_id, project_id))
        if membership is None:
            self._session.add(
                ProjectMembershipRow(user_id=user_id, project_id=project_id, role="admin")
            )
        else:
            membership.role = "admin"
        await self._record_activity(
            None, user_id, project_id, "first_project_admin_bootstrapped", "succeeded", now
        )

    async def list_project_members(
        self, *, actor_id: UUID, project_id: UUID
    ) -> tuple[tuple[UUID, str, str, bool], ...]:
        actor_role = await self._session.scalar(
            select(ProjectMembershipRow.role).where(
                ProjectMembershipRow.user_id == actor_id,
                ProjectMembershipRow.project_id == project_id,
            )
        )
        if actor_role != "admin":
            raise self._authorization_error()
        rows = (
            await self._session.execute(
                select(
                    self._user.id,
                    self._user.name,
                    ProjectMembershipRow.role,
                    self._user.active,
                )
                .join(self._user, self._user.id == ProjectMembershipRow.user_id)
                .where(ProjectMembershipRow.project_id == project_id)
                .order_by(self._user.name)
            )
        ).all()
        return tuple((user_id, name, role, active) for user_id, name, role, active in rows)

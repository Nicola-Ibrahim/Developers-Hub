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
from devops_platform.domain.errors import DomainError
from devops_platform.infra.persistence.models.project_access import ProjectMembershipRow, ProjectRow
from identity.infra.persistence.models.user import InternalUserRow

AuditActivity = Callable[[UUID | None, UUID, UUID | None, str, str, datetime], Awaitable[None]]
ValidationErrorFactory = Callable[[str], Exception]
AuthorizationErrorFactory = Callable[[], Exception]


async def project_memberships(
    session: AsyncSession, user_id: UUID
) -> tuple[tuple[UUID, str, str], ...]:
    rows = (
        await session.execute(
            select(ProjectMembershipRow.project_id, ProjectRow.name, ProjectMembershipRow.role)
            .join(ProjectRow, ProjectRow.id == ProjectMembershipRow.project_id)
            .where(ProjectMembershipRow.user_id == user_id)
            .order_by(ProjectRow.name)
        )
    ).all()
    return tuple((project_id, name, role) for project_id, name, role in rows)


async def lock_named_project(session: AsyncSession, name: str) -> UUID | None:
    project_id: UUID | None = await session.scalar(
        select(ProjectRow.id).where(ProjectRow.name == name).with_for_update()
    )
    return project_id


async def project_membership_role(
    session: AsyncSession, user_id: UUID, project_id: UUID
) -> str | None:
    role: str | None = await session.scalar(
        select(ProjectMembershipRow.role).where(
            ProjectMembershipRow.user_id == user_id,
            ProjectMembershipRow.project_id == project_id,
        )
    )
    return role


async def _project_ids_for_member(session: AsyncSession, user_id: UUID) -> tuple[UUID, ...]:
    ids = await session.scalars(
        select(ProjectMembershipRow.project_id)
        .where(ProjectMembershipRow.user_id == user_id)
        .order_by(ProjectMembershipRow.project_id)
    )
    return tuple(ids.all())


async def lock_user_project_access(
    session: AsyncSession, user_id: UUID, additional_project_ids: tuple[UUID, ...] = ()
) -> tuple[UUID, ...] | None:
    """Lock the known membership scope in UUID order before user/session rows."""
    initial = await _project_ids_for_member(session, user_id)
    project_ids = tuple(sorted(set(initial).union(additional_project_ids)))
    if project_ids:
        locked_projects = await session.scalars(
            select(ProjectRow)
            .where(ProjectRow.id.in_(project_ids))
            .order_by(ProjectRow.id)
            .with_for_update()
        )
        locked_projects.all()
    current = await _project_ids_for_member(session, user_id)
    # A membership added on a project outside the initial lock set means the
    # caller must retry in a fresh transaction to preserve the global order.
    if not set(current).issubset(project_ids):
        return None
    return current


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

    async def lock_account_projects(self, user_id: UUID) -> tuple[UUID, ...]:
        project_ids = await _project_ids_for_member(self._session, user_id)
        for project_id in project_ids:
            await self._session.scalar(
                select(ProjectRow).where(ProjectRow.id == project_id).with_for_update()
            )
        return project_ids

    async def deactivation_conflict(
        self, user_id: UUID, locked_project_ids: tuple[UUID, ...]
    ) -> str | None:
        if await _project_ids_for_member(self._session, user_id) != locked_project_ids:
            return "Project membership changed concurrently; retry account deactivation"
        for project_id in locked_project_ids:
            if await project_membership_role(self._session, user_id, project_id) == "admin":
                access = ProjectAccess(await self.active_admin_count(project_id))
                if not access.may_remove_active_admin(removing_admin=True):
                    return "A project must retain at least one active administrator"
        return None

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
        row = await self._session.get(
            ProjectMembershipRow, (user_id, project_id), with_for_update=True
        )
        try:
            ProjectAccess(
                await self._rules.active_admin_count(project_id)
            ).require_membership_change(
                actor_id=actor_id,
                member_id=user_id,
                current_role=row.role if row is not None else None,
                role=role,
            )
        except DomainError as error:
            raise self._validation_error(error.message) from error
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

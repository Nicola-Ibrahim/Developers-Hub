"""Resolve current project roles under locks held by the calling operation."""

from typing import Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devops_platform.infra.persistence.models.project_access import ProjectMembershipRow, ProjectRow
from identity.infra.persistence.models.user import InternalUserRow

type ProjectRole = Literal["developer", "admin"]


async def project_roles_for_operation(
    session: AsyncSession,
    user_id: UUID,
    project_ids: tuple[UUID, ...],
    *,
    membership_target_id: UUID | None = None,
) -> dict[UUID, ProjectRole]:
    if not project_ids:
        return {}
    # Acquire every project lock before the account and membership rows. Membership
    # changes take the stronger project lock up front to avoid an upgrade deadlock.
    projects = (
        await session.scalars(
            select(ProjectRow.id)
            .where(ProjectRow.id.in_(project_ids))
            .order_by(ProjectRow.id)
            .with_for_update(read=membership_target_id is None)
        )
    ).all()
    if not projects:
        return {}
    account_ids = (user_id,) if membership_target_id is None else (user_id, membership_target_id)
    accounts = await session.scalars(
        select(InternalUserRow)
        .where(InternalUserRow.id.in_(account_ids))
        .order_by(InternalUserRow.id)
        .with_for_update(read=True)
    )
    if not any(account.id == user_id and account.active for account in accounts):
        return {}
    rows = await session.execute(
        select(ProjectMembershipRow.project_id, ProjectMembershipRow.role)
        .where(
            ProjectMembershipRow.user_id == user_id,
            ProjectMembershipRow.project_id.in_(projects),
        )
        .order_by(ProjectMembershipRow.project_id)
        .with_for_update(read=True)
    )
    return {
        project_id: cast(ProjectRole, role)
        for project_id, role in rows
        if role in {"developer", "admin"}
    }


async def resource_request_role(
    session: AsyncSession, user_id: UUID, project_id: UUID
) -> ProjectRole | None:
    return (await project_roles_for_operation(session, user_id, (project_id,))).get(project_id)

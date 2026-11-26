"""Load locked ownership facts for policy evaluation inside the ACTION transaction."""

from dataclasses import replace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devops_platform.domain.value_objects.access_context import AccessContext
from devops_platform.infra.persistence.models.delivery import ApplicationRow
from devops_platform.infra.persistence.models.resources import Resource
from shared.authorization.models import AuthorizationRequest


async def trusted_ownership_facts(
    session: AsyncSession,
    message: object,
    access: AccessContext,
    facts: AuthorizationRequest,
) -> AuthorizationRequest:
    """Read only a target inside the caller's trusted project and lock it."""
    application_id = getattr(message, "application_id", None)
    if isinstance(application_id, UUID):
        row = await session.scalar(
            select(ApplicationRow)
            .where(
                ApplicationRow.id == application_id,
                ApplicationRow.project_id == access.project_id,
            )
            .with_for_update()
        )
        return replace(facts, owner_id=row.owner_id if row is not None else None)

    resource_id = getattr(message, "resource_id", None)
    if isinstance(resource_id, UUID):
        row = await session.scalar(
            select(Resource)
            .where(
                Resource.id == resource_id,
                Resource.project_id == access.project_id,
            )
            .with_for_update()
        )
        return replace(facts, owner_id=row.owner_id if row is not None else None)
    return facts

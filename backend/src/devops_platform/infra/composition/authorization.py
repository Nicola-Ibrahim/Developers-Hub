"""Load locked ownership facts for policy evaluation inside the ACTION transaction."""

from dataclasses import replace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devops_platform.domain.value_objects.access_context import AccessContext
from devops_platform.infra.persistence.models.delivery import ApplicationRow
from devops_platform.infra.persistence.models.resources import Operation, Resource
from shared.authorization.models import AuthorizationRequest


async def trusted_ownership_facts(
    session: AsyncSession,
    message: object,
    access: AccessContext,
    facts: AuthorizationRequest,
) -> AuthorizationRequest:
    """Read existence and owner facts using only the caller's locked project target."""
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
        return replace(
            facts,
            owner_id=row.owner_id if row is not None else None,
            target_exists=row is not None,
        )

    operation_id = getattr(message, "operation_id", None)
    if isinstance(operation_id, UUID):
        result = await session.execute(
            select(Operation.id, Resource.owner_id)
            .join(Resource, Resource.id == Operation.resource_id)
            .where(
                Operation.id == operation_id,
                Resource.project_id == access.project_id,
            )
            .with_for_update(of=Resource)
        )
        operation = result.first()
        return replace(
            facts,
            owner_id=operation.owner_id if operation is not None else None,
            target_exists=operation is not None,
        )

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
        return replace(
            facts,
            owner_id=row.owner_id if row is not None else None,
            target_exists=row is not None,
        )
    return facts

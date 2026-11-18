"""Application rules and DTO construction for internal browser identity."""

from uuid import UUID

from identity.domain.records import MembershipDetails, SessionPrincipal


def principal_for_project(
    *,
    user_id: UUID,
    user_name: str,
    session_id: UUID,
    memberships: tuple[MembershipDetails, ...],
    project_id: UUID | None,
    csrf_token: str,
) -> SessionPrincipal:
    membership = next((item for item in memberships if item.project_id == project_id), None)
    return SessionPrincipal(
        user_id=user_id,
        user_name=user_name,
        session_id=session_id,
        project_id=membership.project_id if membership else None,
        project_name=membership.project_name if membership else None,
        role=membership.role if membership else None,
        scopes=("catalog:read", "resources:read", "resources:write", "connections:read")
        if membership
        else (),
        memberships=memberships,
        csrf_token=csrf_token,
    )

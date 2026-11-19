"""Composition bridge for Identity workflows using Platform project access SQL."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devops_platform.infra.persistence.models.project_access import ProjectMembershipRow
from devops_platform.infra.persistence.repositories.project_access import (
    SQLAlchemyProjectAccessRepository,
    SQLAlchemyProjectAccessRules,
    lock_named_project,
    lock_user_project_access,
    project_membership_role,
    project_memberships,
)
from identity.domain.aggregates.api_token import ApiTokenAuthenticationDetails
from identity.domain.browser_errors import BrowserAuthenticationRejected
from identity.domain.errors import IdentityValidationError
from identity.domain.interfaces.project_access import IdentityProjectAccess
from identity.infra.persistence.models.api_token import ApiAccessTokenRow
from identity.infra.persistence.models.user import InternalUserRow
from identity.infra.persistence.repositories.api_tokens import SQLAlchemyApiTokenRepository
from identity.infra.persistence.repositories.sessions import SQLAlchemySessionRepository
from identity.infra.persistence.repositories.users import SQLAlchemyUserRepository


class SqlAlchemyIdentityProjectAccess:
    """Adapt Platform project-access SQL to Identity's same-session port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._rules = SQLAlchemyProjectAccessRules(session)

    async def project_memberships(self, user_id: UUID) -> tuple[tuple[UUID, str, str], ...]:
        return await project_memberships(self._session, user_id)

    async def lock_user_project_access(
        self, user_id: UUID, additional_project_ids: tuple[UUID, ...] = ()
    ) -> tuple[UUID, ...] | None:
        return await lock_user_project_access(self._session, user_id, additional_project_ids)

    async def project_membership_role(self, user_id: UUID, project_id: UUID) -> str | None:
        return await project_membership_role(self._session, user_id, project_id)

    async def lock_named_project(self, name: str) -> UUID | None:
        return await lock_named_project(self._session, name)

    async def lock_project_membership(self, user_id: UUID, project_id: UUID) -> bool:
        membership = await self._session.get(
            ProjectMembershipRow, (user_id, project_id), with_for_update=True
        )
        return membership is not None

    async def find_token_credential(self, digest: str) -> ApiTokenAuthenticationDetails | None:
        row = (
            await self._session.execute(
                select(ApiAccessTokenRow, InternalUserRow.active, ProjectMembershipRow.role)
                .join(InternalUserRow, InternalUserRow.id == ApiAccessTokenRow.user_id)
                .join(
                    ProjectMembershipRow,
                    (ProjectMembershipRow.user_id == ApiAccessTokenRow.user_id)
                    & (ProjectMembershipRow.project_id == ApiAccessTokenRow.project_id),
                )
                .where(ApiAccessTokenRow.digest == digest)
                .with_for_update(
                    read=True,
                    of=(ApiAccessTokenRow, InternalUserRow, ProjectMembershipRow),
                )
            )
        ).one_or_none()
        if row is None:
            return None
        token, active, role = row
        return ApiTokenAuthenticationDetails(
            token_id=token.id,
            user_id=token.user_id,
            project_id=token.project_id,
            role=role,
            scopes=tuple(token.scopes),
            user_active=active,
            expires_at=token.expires_at,
            revoked_at=token.revoked_at,
        )

    async def lock_account_projects(self, user_id: UUID) -> tuple[UUID, ...]:
        return await self._rules.lock_account_projects(user_id)

    async def deactivation_conflict(
        self, user_id: UUID, locked_project_ids: tuple[UUID, ...]
    ) -> str | None:
        return await self._rules.deactivation_conflict(user_id, locked_project_ids)

    async def demote_admin_memberships(self, user_id: UUID) -> None:
        await self._rules.demote_admin_memberships(user_id)


def identity_project_access_for_session(session: AsyncSession) -> IdentityProjectAccess:
    return SqlAlchemyIdentityProjectAccess(session)


def identity_repositories_for_session(
    session: AsyncSession,
) -> tuple[SQLAlchemyUserRepository, SQLAlchemySessionRepository]:
    project_access = identity_project_access_for_session(session)
    users = SQLAlchemyUserRepository(session, project_access)
    sessions = SQLAlchemySessionRepository(session, users, project_access)
    return users, sessions


def api_token_repository_for_session(session: AsyncSession) -> SQLAlchemyApiTokenRepository:
    return SQLAlchemyApiTokenRepository(session, identity_project_access_for_session(session))


def project_access_repository_for_session(
    session: AsyncSession,
) -> SQLAlchemyProjectAccessRepository:
    """Build the Platform membership repository directly on the caller's session."""
    rules = SQLAlchemyProjectAccessRules(session)
    _users, activity = identity_repositories_for_session(session)
    return SQLAlchemyProjectAccessRepository(
        session=session,
        rules=rules,
        user_row=InternalUserRow,
        record_activity=activity.record_project_access_activity,
        validation_error=IdentityValidationError,
        authorization_error=BrowserAuthenticationRejected,
    )

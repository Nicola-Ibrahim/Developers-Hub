"""Composition bridge for Identity workflows using Platform project access SQL."""

from sqlalchemy.ext.asyncio import AsyncSession

from devops_platform.infra.persistence.repositories.project_access import (
    SQLAlchemyProjectAccessRepository,
    SQLAlchemyProjectAccessRules,
)
from identity.domain.browser_errors import BrowserAuthenticationRejected
from identity.domain.errors import IdentityValidationError
from identity.infra.persistence.models.user import InternalUserRow
from identity.infra.persistence.repositories.accounts_sessions import SQLAlchemyIdentityRepository


def identity_repository_for_session(session: AsyncSession) -> SQLAlchemyIdentityRepository:
    rules = SQLAlchemyProjectAccessRules(session)
    identity = SQLAlchemyIdentityRepository(session, project_access_rules=rules)
    access = SQLAlchemyProjectAccessRepository(
        session=session,
        rules=rules,
        user_row=InternalUserRow,
        record_activity=identity.record_project_access_activity,
        validation_error=IdentityValidationError,
        authorization_error=BrowserAuthenticationRejected,
    )
    identity.attach_project_access_repository(access)
    return identity

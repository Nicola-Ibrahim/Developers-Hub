"""Aggregate ORM metadata for Alembic schema operations."""

from sqlalchemy import MetaData

from devops_platform.infra.persistence.models import delivery as _delivery_models
from devops_platform.infra.persistence.models import project as _project_models
from devops_platform.infra.persistence.models import project_access as _project_access_models
from devops_platform.infra.persistence.models import resources as _platform_models
from identity.infra.persistence.models import activity as _identity_activity
from identity.infra.persistence.models import api_token as _identity_tokens
from identity.infra.persistence.models import session as _identity_sessions
from identity.infra.persistence.models import user as _identity_users
from shared.infra.persistence import audit as _audit_models
from shared.infra.persistence.base import Base


def registered_metadata() -> MetaData:
    """Import every mapping owner and return their shared metadata."""
    # Keep explicit references so imports remain intentional and discoverable.
    _ = (
        _audit_models,
        _identity_activity,
        _identity_tokens,
        _identity_sessions,
        _identity_users,
        _platform_models,
        _project_models,
        _project_access_models,
        _delivery_models,
    )
    return Base.metadata

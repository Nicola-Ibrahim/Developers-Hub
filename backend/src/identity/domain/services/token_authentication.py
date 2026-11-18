"""API token credential eligibility rules."""

from datetime import datetime
from typing import Literal, cast

from identity.domain.aggregates.api_token import (
    ApiTokenAuthenticationDetails,
    AuthenticatedPrincipal,
)
from identity.domain.errors import AuthenticationRejected


def authenticate_api_token_credentials(
    snapshot: ApiTokenAuthenticationDetails | None, now: datetime
) -> AuthenticatedPrincipal:
    if snapshot is None:
        raise AuthenticationRejected()
    role = snapshot.role
    if (
        not snapshot.user_active
        or snapshot.revoked_at is not None
        or snapshot.expires_at <= now
        or (role != "developer" and role != "admin")
    ):
        raise AuthenticationRejected()
    return AuthenticatedPrincipal(
        user_id=snapshot.user_id,
        project_id=snapshot.project_id,
        token_id=snapshot.token_id,
        role=cast("Literal['developer', 'admin']", role),
        scopes=frozenset(snapshot.scopes),
    )

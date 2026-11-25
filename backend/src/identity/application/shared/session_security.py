from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.records import SessionPrincipal
from identity.domain.session_errors import SessionAuthenticationRejected

DigestSecret = Callable[[str], str]


def require_allowed_origin(origin: str | None, allowed_origins: tuple[str, ...]) -> None:
    allowed = {value.rstrip("/") for value in allowed_origins}
    if origin is None or origin.rstrip("/") not in allowed:
        raise SessionAuthenticationRejected()


async def authorize_session_operation(
    repository: SessionRepository,
    *,
    token_digest: str,
    project_id: UUID | None,
    now: datetime,
    mutate: bool,
    csrf_digest: Callable[[], str | None],
) -> SessionPrincipal:
    principal = await repository.authorize_session_operation(
        token_digest, project_id, now, lock_for_mutation=mutate
    )
    if principal is None:
        raise SessionAuthenticationRejected()
    if mutate:
        digest = csrf_digest()
        if digest is None or not await repository.validate_csrf(token_digest, digest):
            raise SessionAuthenticationRejected()
    return principal


async def authorize_session_mutation(
    repository: SessionRepository,
    digest_secret: DigestSecret,
    allowed_origins: tuple[str, ...],
    session_token: str,
    csrf_token: str,
    origin: str | None,
    *,
    now: datetime,
) -> SessionPrincipal:
    require_allowed_origin(origin, allowed_origins)
    return await authorize_session_operation(
        repository,
        token_digest=digest_secret(session_token),
        project_id=None,
        now=now,
        mutate=True,
        csrf_digest=lambda: digest_secret(csrf_token),
    )

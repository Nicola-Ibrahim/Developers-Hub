from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from identity.domain.browser_errors import BrowserAuthenticationRejected
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.records import SessionPrincipal

Clock = Callable[[], datetime]
DigestSecret = Callable[[str], str]


def require_browser_origin(origin: str | None, allowed_origins: tuple[str, ...]) -> None:
    allowed = {value.rstrip("/") for value in allowed_origins}
    if origin is None or origin.rstrip("/") not in allowed:
        raise BrowserAuthenticationRejected()


async def authorize_browser_operation(
    repository: SessionRepository,
    *,
    token_digest: str,
    project_id: UUID | None,
    now: datetime,
    mutate: bool,
    csrf_digest: Callable[[], str | None],
) -> SessionPrincipal:
    principal = await repository.authorize_browser_operation(
        token_digest, project_id, now, lock_for_mutation=mutate
    )
    if principal is None:
        raise BrowserAuthenticationRejected()
    if mutate:
        digest = csrf_digest()
        if digest is None or not await repository.validate_csrf(token_digest, digest):
            raise BrowserAuthenticationRejected()
    return principal


class BrowserMutationAuthorizer:
    def __init__(
        self,
        repository: SessionRepository,
        clock: Clock,
        digest_secret: DigestSecret,
        allowed_origins: tuple[str, ...],
    ) -> None:
        self.repository = repository
        self.clock = clock
        self.digest_secret = digest_secret
        self.allowed_origins = allowed_origins

    async def authorize_mutation(
        self, session_token: str, csrf_token: str, origin: str | None
    ) -> SessionPrincipal:
        require_browser_origin(origin, self.allowed_origins)
        return await authorize_browser_operation(
            self.repository,
            token_digest=self.digest_secret(session_token),
            project_id=None,
            now=self.clock(),
            mutate=True,
            csrf_digest=lambda: self.digest_secret(csrf_token),
        )

from collections.abc import Callable
from datetime import datetime

from identity.application.authentication.authenticate_session.handler import authenticate_session
from identity.application.profile.profile_query import ProfileQuery, SecurityHistoryQuery
from identity.application.profile.update_profile import UpdateProfileCommand
from identity.application.shared.session_security import BrowserMutationAuthorizer
from identity.domain.browser_errors import BrowserAuthenticationRejected
from identity.domain.errors import IdentityValidationError
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository
from identity.domain.records import AccountProfile, SecurityActivity


class ProfileHandler:
    def __init__(
        self,
        users: UserRepository,
        sessions: SessionRepository,
        clock: Callable[[], datetime],
        digest: Callable[[str], str],
        allowed_origins: tuple[str, ...],
    ) -> None:
        self.users, self.sessions = users, sessions
        self.clock, self.digest, self.allowed_origins = clock, digest, allowed_origins

    async def execute(self, message: ProfileQuery | UpdateProfileCommand) -> AccountProfile:
        if isinstance(message, ProfileQuery):
            return await self._load(message)
        return await self._update(message)

    async def _load(self, query: ProfileQuery) -> AccountProfile:
        principal = await authenticate_session(
            self.sessions, self.clock, self.digest, query.session_token
        )
        profile = await self.users.load_profile(principal.user_id)
        if profile is None:
            raise BrowserAuthenticationRejected()
        return profile

    async def _update(self, command: UpdateProfileCommand) -> AccountProfile:
        if command.display_name is not None and (
            not command.display_name.strip() or len(command.display_name) > 100
        ):
            raise IdentityValidationError("Display name must contain 1 to 100 characters")
        principal = await BrowserMutationAuthorizer(
            self.sessions, self.clock, self.digest, self.allowed_origins
        ).authorize_mutation(command.session_token, command.csrf_token, command.origin)
        profile = await self.users.update_profile(
            user_id=principal.user_id,
            display_name=command.display_name.strip() if command.display_name is not None else None,
            now=self.clock(),
        )
        if profile is None:
            raise BrowserAuthenticationRejected()
        return profile


class SecurityHistoryHandler:
    def __init__(
        self,
        users: UserRepository,
        sessions: SessionRepository,
        clock: Callable[[], datetime],
        digest: Callable[[str], str],
    ) -> None:
        self.users, self.sessions = users, sessions
        self.clock, self.digest = clock, digest

    async def execute(self, query: SecurityHistoryQuery) -> tuple[SecurityActivity, ...]:
        principal = await authenticate_session(
            self.sessions, self.clock, self.digest, query.session_token
        )
        return await self.users.list_security_history(principal.user_id, limit=100)

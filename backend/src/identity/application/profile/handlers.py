from datetime import UTC, datetime

from identity.application.profile.profile_query import ProfileQuery, SecurityHistoryQuery
from identity.application.profile.update_profile import UpdateProfileCommand
from identity.domain.errors import IdentityValidationError
from identity.domain.interfaces.user_repository import UserRepository
from identity.domain.records import AccountProfile, SecurityActivity
from identity.domain.session_errors import SessionAuthenticationRejected


class ReadProfileHandler:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    async def execute(self, query: ProfileQuery) -> AccountProfile:
        profile = await self.users.load_profile(query.actor_id)
        if profile is None:
            raise SessionAuthenticationRejected()
        return profile


class UpdateProfileHandler:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    async def execute(self, command: UpdateProfileCommand) -> AccountProfile:
        if command.display_name is not None and (
            not command.display_name.strip() or len(command.display_name) > 100
        ):
            raise IdentityValidationError("Display name must contain 1 to 100 characters")
        profile = await self.users.update_profile(
            user_id=command.actor_id,
            display_name=command.display_name.strip() if command.display_name is not None else None,
            now=datetime.now(UTC),
        )
        if profile is None:
            raise SessionAuthenticationRejected()
        return profile


class SecurityHistoryHandler:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    async def execute(self, query: SecurityHistoryQuery) -> tuple[SecurityActivity, ...]:
        return await self.users.list_security_history(query.actor_id, limit=100)

from datetime import UTC, datetime

from identity.application.profile.update_profile.command import UpdateProfileCommand
from identity.domain.interfaces.user_repository import UserRepository
from identity.domain.records import AccountProfile
from identity.domain.session_errors import SessionAuthenticationRejected


class UpdateProfileHandler:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    async def execute(self, command: UpdateProfileCommand) -> AccountProfile:
        profile = await self.users.update_profile(
            user_id=command.actor_id,
            display_name=command.display_name,
            now=datetime.now(UTC),
        )
        if profile is None:
            raise SessionAuthenticationRejected()
        return profile

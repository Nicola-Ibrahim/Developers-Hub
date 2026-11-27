from identity.application.profile.read_profile.query import ProfileQuery
from identity.domain.interfaces.user_repository import UserRepository
from identity.domain.records import AccountProfile
from identity.domain.session_errors import SessionAuthenticationRejected


class ReadProfileHandler:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    async def execute(self, query: ProfileQuery) -> AccountProfile:
        profile = await self.users.load_profile(query.actor_id)
        if profile is None:
            raise SessionAuthenticationRejected()
        return profile

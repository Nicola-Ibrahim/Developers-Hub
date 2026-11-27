from identity.application.profile.security_history.query import SecurityHistoryQuery
from identity.domain.interfaces.user_repository import UserRepository
from identity.domain.records import SecurityActivity


class SecurityHistoryHandler:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    async def execute(self, query: SecurityHistoryQuery) -> tuple[SecurityActivity, ...]:
        return await self.users.list_security_history(query.actor_id, limit=100)

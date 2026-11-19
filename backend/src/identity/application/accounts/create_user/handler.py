import asyncio
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from identity.application.accounts.create_user.command import CreateUserCommand
from identity.application.interfaces.browser_transactions import BrowserTransaction
from identity.application.interfaces.security import PasswordHasher
from identity.domain.browser_credentials import validate_password
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository
from identity.domain.value_objects.user_name import UserName

Clock = Callable[[], datetime]


class CreateUserHandler:
    def __init__(
        self, transaction: BrowserTransaction, passwords: PasswordHasher, clock: Clock
    ) -> None:
        self.transaction = transaction
        self.passwords = passwords
        self.clock = clock

    async def execute(self, command: CreateUserCommand) -> UUID:
        name = UserName.parse(command.user_name).value
        validate_password(command.password)
        encoded = await asyncio.to_thread(self.passwords.hash, command.password)

        async def create(users: UserRepository, _sessions: SessionRepository) -> UUID:
            return await users.create_user(name, encoded, command.actor_id, self.clock())

        return await self.transaction.run(create)

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from identity.application.accounts.create_user.command import CreateUserCommand
from identity.application.interfaces.identity_transactions import IdentityTransaction
from identity.application.interfaces.security import PasswordHasher
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository


class CreateUserHandler:
    def __init__(self, transaction: IdentityTransaction, passwords: PasswordHasher) -> None:
        self.transaction = transaction
        self.passwords = passwords

    async def execute(self, command: CreateUserCommand) -> UUID:
        encoded = await asyncio.to_thread(self.passwords.hash, command.password)

        async def create(users: UserRepository, _sessions: SessionRepository) -> UUID:
            return await users.create_user(
                command.user_name, encoded, command.actor_id, datetime.now(UTC)
            )

        return await self.transaction.run(create)

import asyncio
from datetime import UTC, datetime

from identity.application.accounts.complete_password_setup.command import (
    CompletePasswordSetupCommand,
)
from identity.application.interfaces.identity_transactions import IdentityTransaction
from identity.application.interfaces.security import PasswordHasher, TokenHasher
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository


class CompletePasswordSetupHandler:
    def __init__(
        self,
        transaction: IdentityTransaction,
        passwords: PasswordHasher,
        hasher: TokenHasher,
    ) -> None:
        self.transaction = transaction
        self.passwords = passwords
        self.hasher = hasher

    async def execute(self, command: CompletePasswordSetupCommand) -> bool:
        encoded = await asyncio.to_thread(self.passwords.hash, command.new_password)

        async def consume(users: UserRepository, sessions: SessionRepository) -> bool:
            now = datetime.now(UTC)
            user_id = await users.consume_password_setup(
                digest=self.hasher.digest(command.secret), password_hash=encoded, now=now
            )
            if user_id is None:
                return False
            await sessions.revoke_user_sessions(user_id, now)
            return True

        return await self.transaction.run(consume)

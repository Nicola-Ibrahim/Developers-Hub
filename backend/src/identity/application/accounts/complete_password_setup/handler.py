import asyncio
from collections.abc import Callable
from datetime import datetime

from identity.application.accounts.complete_password_setup.command import (
    CompletePasswordSetupCommand,
)
from identity.application.interfaces.browser_transactions import BrowserTransaction
from identity.application.interfaces.security import PasswordHasher
from identity.domain.browser_credentials import validate_password
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository

Clock = Callable[[], datetime]

DigestSecret = Callable[[str], str]


class CompletePasswordSetupHandler:
    def __init__(
        self,
        transaction: BrowserTransaction,
        passwords: PasswordHasher,
        clock: Clock,
        digest_secret: DigestSecret,
    ) -> None:
        self.transaction = transaction
        self.passwords = passwords
        self.clock = clock
        self.digest_secret = digest_secret

    async def execute(self, command: CompletePasswordSetupCommand) -> bool:
        validate_password(command.new_password)
        encoded = await asyncio.to_thread(self.passwords.hash, command.new_password)

        async def consume(users: UserRepository, sessions: SessionRepository) -> bool:
            now = self.clock()
            user_id = await users.consume_password_setup(
                digest=self.digest_secret(command.secret), password_hash=encoded, now=now
            )
            if user_id is None:
                return False
            await sessions.revoke_user_sessions(user_id, now)
            return True

        return await self.transaction.run(consume)

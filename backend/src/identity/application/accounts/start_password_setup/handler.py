from datetime import UTC, datetime, timedelta

from identity.application.accounts.start_password_setup.command import StartPasswordSetupCommand
from identity.application.interfaces.identity_transactions import IdentityTransaction
from identity.application.interfaces.security import TokenGenerator, TokenHasher
from identity.domain.interfaces.session_repository import SessionRepository
from identity.domain.interfaces.user_repository import UserRepository


class StartPasswordSetupHandler:
    def __init__(
        self,
        transaction: IdentityTransaction,
        generator: TokenGenerator,
        hasher: TokenHasher,
    ) -> None:
        self.transaction = transaction
        self.generator = generator
        self.hasher = hasher

    async def execute(self, command: StartPasswordSetupCommand) -> str:
        secret, now = self.generator.generate(), datetime.now(UTC)

        async def issue(users: UserRepository, _sessions: SessionRepository) -> None:
            await users.issue_password_setup(
                user_id=command.user_id,
                digest=self.hasher.digest(secret),
                expires_at=now + timedelta(hours=1),
                actor_id=command.actor_id,
                now=now,
            )

        await self.transaction.run(issue)
        return secret

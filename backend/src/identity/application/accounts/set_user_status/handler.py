from collections.abc import Callable
from datetime import datetime

from identity.application.accounts.set_user_status.command import SetUserStatusCommand
from identity.application.interfaces.browser_transactions import BrowserTransaction

Clock = Callable[[], datetime]


class SetUserStatusHandler:
    def __init__(self, transaction: BrowserTransaction, clock: Clock) -> None:
        self.transaction = transaction
        self.clock = clock

    async def execute(self, command: SetUserStatusCommand) -> None:
        await self.transaction.run(
            lambda repo: repo.set_user_active(
                actor_id=command.actor_id,
                user_id=command.user_id,
                active=command.active,
                now=self.clock(),
            )
        )

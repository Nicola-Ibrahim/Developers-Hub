from collections.abc import Callable
from datetime import datetime

from identity.application.accounts.bootstrap_first_admin.command import BootstrapFirstAdminCommand
from identity.application.interfaces.browser_transactions import BrowserTransaction

Clock = Callable[[], datetime]


class BootstrapFirstAdminHandler:
    def __init__(self, transaction: BrowserTransaction, clock: Clock) -> None:
        self.transaction = transaction
        self.clock = clock

    async def execute(self, command: BootstrapFirstAdminCommand) -> None:
        await self.transaction.run(
            lambda repo: repo.bootstrap_first_project_admin(
                user_id=command.user_id, project_id=command.project_id, now=self.clock()
            )
        )

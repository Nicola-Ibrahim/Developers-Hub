from collections.abc import Callable
from datetime import datetime

from identity.application.interfaces.browser_transactions import (
    BrowserRepository,
    BrowserTransaction,
)
from identity.application.interfaces.project_access_bridge import ProjectAccessBridge
from identity.application.project_access.manage_project_membership.command import (
    ManageProjectMembershipCommand,
    SetProjectMembershipCommand,
)
from identity.application.shared.session_security import BrowserMutationAuthorizer, DigestSecret

Clock = Callable[[], datetime]


class ManageProjectMembershipHandler:
    def __init__(
        self,
        transaction: BrowserTransaction,
        project_access: ProjectAccessBridge,
        clock: Clock,
        digest_secret: DigestSecret,
        allowed_origins: tuple[str, ...],
    ) -> None:
        self.transaction = transaction
        self.project_access = project_access
        self.clock = clock
        self.digest_secret = digest_secret
        self.allowed_origins = allowed_origins

    async def execute(self, command: ManageProjectMembershipCommand) -> None:
        async def action(repository: BrowserRepository) -> None:
            await repository.lock_project_membership_admin_scope(command.project_id)
            principal = await BrowserMutationAuthorizer(
                repository, self.clock, self.digest_secret, self.allowed_origins
            ).authorize_mutation(command.session_token, command.csrf_token, command.origin)
            await self.project_access.set_membership(
                repository,
                actor_id=principal.user_id,
                user_id=command.user_id,
                project_id=command.project_id,
                role=command.role,
                now=self.clock(),
            )

        await self.transaction.run(action)


class SetProjectMembershipHandler:
    def __init__(
        self, transaction: BrowserTransaction, project_access: ProjectAccessBridge, clock: Clock
    ) -> None:
        self.transaction = transaction
        self.project_access = project_access
        self.clock = clock

    async def execute(self, command: SetProjectMembershipCommand) -> None:
        await self.transaction.run(
            lambda repository: self.project_access.set_membership(
                repository,
                actor_id=command.actor_id,
                user_id=command.user_id,
                project_id=command.project_id,
                role=command.role,
                now=self.clock(),
            )
        )

from collections.abc import Callable
from datetime import datetime

from identity.application.authentication.authenticate_session.handler import authenticate_session
from identity.application.interfaces.browser_transactions import (
    BrowserRepository,
    BrowserTransaction,
)
from identity.application.interfaces.project_access_bridge import ProjectAccessBridge
from identity.application.project_access.list_project_members.query import ListProjectMembersQuery
from identity.domain.records import ProjectMemberDetails


class ListProjectMembersHandler:
    def __init__(
        self,
        transaction: BrowserTransaction,
        project_access: ProjectAccessBridge,
        clock: Callable[[], datetime],
        digest_secret: Callable[[str], str],
    ) -> None:
        self.transaction = transaction
        self.project_access = project_access
        self.clock = clock
        self.digest_secret = digest_secret

    async def execute(self, query: ListProjectMembersQuery) -> tuple[ProjectMemberDetails, ...]:
        async def action(repository: BrowserRepository) -> tuple[ProjectMemberDetails, ...]:
            principal = await authenticate_session(
                repository, self.clock, self.digest_secret, query.session_token, query.project_id
            )
            return await self.project_access.list_project_members(
                repository, actor_id=principal.user_id, project_id=query.project_id
            )

        return await self.transaction.run(action)

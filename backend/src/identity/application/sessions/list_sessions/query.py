from dataclasses import dataclass
from uuid import UUID

from identity.application.sessions.list_sessions.result import SessionDetails
from shared.dispatch import Query


@dataclass(frozen=True, slots=True)
class ListSessionsQuery(Query[tuple[SessionDetails, ...]]):
    actor_id: UUID
    current_session_id: UUID

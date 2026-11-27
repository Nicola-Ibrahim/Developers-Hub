from uuid import UUID

from pydantic import BaseModel, ConfigDict

from identity.application.sessions.list_sessions.result import SessionDetails
from shared.dispatch import Query


class ListSessionsQuery(BaseModel, Query[tuple[SessionDetails, ...]]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    actor_id: UUID
    current_session_id: UUID

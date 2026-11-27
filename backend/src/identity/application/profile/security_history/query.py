from uuid import UUID

from pydantic import BaseModel, ConfigDict

from identity.domain.records import SecurityActivity
from shared.dispatch import Query


class SecurityHistoryQuery(BaseModel, Query[tuple[SecurityActivity, ...]]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    actor_id: UUID

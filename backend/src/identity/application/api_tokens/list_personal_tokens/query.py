from uuid import UUID

from pydantic import BaseModel, ConfigDict

from identity.domain.records import PersonalApiToken
from shared.dispatch import Query


class ListPersonalTokensQuery(BaseModel, Query[tuple[PersonalApiToken, ...]]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    actor_id: UUID
    project_id: UUID | None = None

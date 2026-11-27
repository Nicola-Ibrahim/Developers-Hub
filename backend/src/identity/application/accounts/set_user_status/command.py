from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SetUserStatusCommand(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    actor_id: UUID
    user_id: UUID
    active: bool

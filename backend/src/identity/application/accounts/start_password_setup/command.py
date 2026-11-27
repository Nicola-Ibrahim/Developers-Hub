from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StartPasswordSetupCommand(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    user_id: UUID
    actor_id: UUID

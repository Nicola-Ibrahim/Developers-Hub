from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RevokeApiTokenCommand(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    token_id: UUID

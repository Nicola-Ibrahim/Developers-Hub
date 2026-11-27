from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.dispatch import Command


class RevokePersonalTokenCommand(BaseModel, Command[bool]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    actor_id: UUID
    token_id: UUID

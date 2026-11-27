from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.dispatch import Command


class RevokeAllSessionsCommand(BaseModel, Command[int]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    actor_id: UUID

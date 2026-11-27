from uuid import UUID

from pydantic import BaseModel, ConfigDict

from identity.domain.records import PersonalApiToken
from shared.dispatch import Command


class RotatePersonalTokenCommand(BaseModel, Command[tuple[PersonalApiToken, str] | None]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    actor_id: UUID
    token_id: UUID

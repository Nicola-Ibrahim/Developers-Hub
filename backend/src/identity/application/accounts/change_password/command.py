from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from identity.domain.password_policy import validate_password
from shared.dispatch import Command


class ChangePasswordCommand(BaseModel, Command[None]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    actor_id: UUID
    actor_name: str
    current_password: str = Field(repr=False)
    new_password: str = Field(repr=False)

    def validate_new_password(self) -> None:
        """Apply the policy after the current credential has been verified."""
        validate_password(self.new_password)

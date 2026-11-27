from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from identity.domain.errors import IdentityValidationError
from identity.domain.records import AccountProfile
from shared.dispatch import Command


class UpdateProfileCommand(BaseModel, Command[AccountProfile]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    actor_id: UUID
    display_name: str | None

    @field_validator("display_name")
    @classmethod
    def check_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        display_name = value.strip()
        if not display_name or len(value) > 100:
            raise IdentityValidationError("Display name must contain 1 to 100 characters")
        return display_name

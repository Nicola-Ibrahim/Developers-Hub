from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from identity.domain.errors import IdentityValidationError
from identity.domain.records import PersonalApiToken
from shared.dispatch import Command


class CreatePersonalTokenCommand(BaseModel, Command[tuple[PersonalApiToken, str]]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    actor_id: UUID
    project_id: UUID | None
    name: str
    scopes: tuple[str, ...]
    hours: int

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        name = value.strip()
        if not name or len(value) > 100:
            raise IdentityValidationError("Invalid token name or duration")
        return name

    @field_validator("hours")
    @classmethod
    def check_hours(cls, value: int) -> int:
        if not 1 <= value <= 720:
            raise IdentityValidationError("Invalid token name or duration")
        return value

    def require_project_id(self) -> UUID:
        if self.project_id is None:
            raise IdentityValidationError("Select a project before creating a token")
        return self.project_id

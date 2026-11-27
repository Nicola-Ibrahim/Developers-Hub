from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from identity.domain.password_policy import validate_password
from identity.domain.value_objects.user_name import UserName


class CreateUserCommand(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    user_name: str
    password: str = Field(repr=False)
    actor_id: UUID | None = None

    @field_validator("user_name")
    @classmethod
    def normalize_user_name(cls, value: str) -> str:
        return UserName.parse(value).value

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        validate_password(value)
        return value

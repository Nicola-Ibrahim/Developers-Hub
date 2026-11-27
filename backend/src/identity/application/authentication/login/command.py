from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from identity.application.authentication.login.result import LoginResult
from identity.domain.errors import IdentityValidationError
from identity.domain.value_objects.user_name import UserName
from shared.dispatch import Command


class LoginCommand(BaseModel, Command[LoginResult]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    user_name: str
    password: str = Field(repr=False)
    project_id: UUID | None

    @field_validator("user_name")
    @classmethod
    def normalize_user_name(cls, value: str) -> str:
        return UserName.parse(value).value

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        if not 1 <= len(value) <= 1024:
            raise IdentityValidationError("Password must contain between 1 and 1024 characters")
        return value

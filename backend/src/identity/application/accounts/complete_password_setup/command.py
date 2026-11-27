from pydantic import BaseModel, ConfigDict, Field, field_validator

from identity.domain.password_policy import validate_password


class CompletePasswordSetupCommand(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    secret: str = Field(repr=False)
    new_password: str = Field(repr=False)

    @field_validator("new_password")
    @classmethod
    def check_password(cls, value: str) -> str:
        validate_password(value)
        return value

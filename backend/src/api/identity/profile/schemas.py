from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from api.core.schemas import Contract


class ProfileView(Contract):
    user_id: UUID = Field(alias="userId")
    user_name: str = Field(alias="userName")
    display_name: str | None = Field(alias="displayName")


class UpdateProfileBody(Contract):
    display_name: str | None = Field(alias="displayName", max_length=100)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Display name cannot be blank")
        return value


class SecurityActivityView(Contract):
    id: UUID
    action: str
    outcome: str
    created_at: datetime = Field(alias="createdAt")

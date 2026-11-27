from pydantic import BaseModel, ConfigDict, Field

from shared.dispatch import Command


class LogoutCommand(BaseModel, Command[None]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    session_token: str = Field(repr=False)

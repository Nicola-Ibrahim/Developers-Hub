from pydantic import BaseModel, ConfigDict, Field

from identity.domain.records import SessionPrincipal
from shared.dispatch import Command


class RotateCsrfCommand(BaseModel, Command[SessionPrincipal]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    session_token: str = Field(repr=False)

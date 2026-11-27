from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from identity.domain.records import SessionPrincipal
from shared.dispatch import Query


class AuthenticateSessionQuery(BaseModel, Query[SessionPrincipal]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    session_token: str = Field(repr=False)
    project_id: UUID | None = None
    csrf_token: str | None = Field(default=None, repr=False)

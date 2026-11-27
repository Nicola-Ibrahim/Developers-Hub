from pydantic import BaseModel, ConfigDict, Field

from identity.domain.aggregates.api_token import AuthenticatedPrincipal
from identity.domain.errors import AuthenticationRejected
from shared.dispatch import Query


class AuthenticateApiTokenQuery(BaseModel, Query[AuthenticatedPrincipal]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    token: str | None = Field(repr=False)

    def require_token(self) -> str:
        if self.token is None or not 32 <= len(self.token) <= 256:
            raise AuthenticationRejected()
        return self.token

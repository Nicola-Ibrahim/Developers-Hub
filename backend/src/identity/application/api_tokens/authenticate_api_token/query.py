from dataclasses import dataclass, field

from identity.domain.aggregates.api_token import AuthenticatedPrincipal
from shared.dispatch import Query


@dataclass(frozen=True, slots=True)
class AuthenticateApiTokenQuery(Query[AuthenticatedPrincipal]):
    token: str | None = field(repr=False)

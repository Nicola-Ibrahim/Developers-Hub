from datetime import UTC, datetime

from identity.application.api_tokens.authenticate_api_token.query import AuthenticateApiTokenQuery
from identity.application.interfaces.security import TokenHasher
from identity.application.interfaces.token_operations import ApiTokenTransaction
from identity.domain.aggregates.api_token import AuthenticatedPrincipal
from identity.domain.errors import AuthenticationRejected
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.domain.services.token_authentication import authenticate_api_token_credentials


class AuthenticateApiTokenHandler:
    def __init__(self, transaction: ApiTokenTransaction, hasher: TokenHasher) -> None:
        self.transaction = transaction
        self.hasher = hasher

    async def execute(self, query: AuthenticateApiTokenQuery) -> AuthenticatedPrincipal:
        return await self.transaction.run(
            lambda repository: authenticate_api_token(
                query, repository, self.hasher, datetime.now(UTC)
            )
        )


async def authenticate_api_token(
    query: AuthenticateApiTokenQuery,
    repository: ApiTokenRepository,
    hasher: TokenHasher,
    now: datetime,
) -> AuthenticatedPrincipal:
    token = query.token
    if token is None or not 32 <= len(token) <= 256:
        raise AuthenticationRejected()
    snapshot = await repository.find_token_credential(hasher.digest(token))
    return authenticate_api_token_credentials(snapshot, now)

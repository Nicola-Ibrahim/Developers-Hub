from identity.application.api_tokens.list_personal_tokens.query import ListPersonalTokensQuery
from identity.domain.interfaces.api_token_repository import ApiTokenRepository
from identity.domain.records import PersonalApiToken


class PersonalTokenQueryHandler:
    def __init__(self, tokens: ApiTokenRepository) -> None:
        self.tokens = tokens

    async def execute(self, query: ListPersonalTokensQuery) -> tuple[PersonalApiToken, ...]:
        return await self.tokens.list_personal_tokens(query.actor_id, query.project_id)

"""Process-wide OPA client lifecycle."""

from collections.abc import AsyncIterator

import httpx
from dishka import Provider, Scope, provide

from shared.authorization.interfaces import AuthorizationDecisionPort
from shared.infra.authorization.opa_client import OpaAuthorizationClient
from shared.infra.settings import Settings


class AuthorizationProvider(Provider):
    @provide(scope=Scope.APP, provides=AuthorizationDecisionPort)
    async def opa_client(self, settings: Settings) -> AsyncIterator[OpaAuthorizationClient]:
        async with httpx.AsyncClient(trust_env=False) as client:
            yield OpaAuthorizationClient(settings.opa_url, client)

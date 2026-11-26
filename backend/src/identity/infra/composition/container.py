"""Identity-owned registrations contributed to the backend Dishka container."""

from dataclasses import dataclass

from dishka import Provider

from identity import application
from identity.infra.composition.action_provider import IdentityActionProvider
from identity.infra.composition.module import IDENTITY_HANDLER_REGISTRY
from identity.infra.composition.providers import IdentityProvider, IdentityTokenScopePolicy
from shared.infra.dispatch import validate_context_messages


@dataclass(frozen=True, slots=True)
class IdentityContainer:
    """Expose Identity's provider registrations and required runtime context."""

    token_scopes: tuple[str, ...]

    def providers(self) -> tuple[Provider, ...]:
        validate_context_messages(IDENTITY_HANDLER_REGISTRY, application)
        return (
            IdentityProvider(),
            IdentityActionProvider(component="identity_action"),
        )

    def context(self) -> dict[type[object], object]:
        return {IdentityTokenScopePolicy: IdentityTokenScopePolicy(self.token_scopes)}

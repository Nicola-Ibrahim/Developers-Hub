"""Identity-owned registrations contributed to the backend Dishka container."""

from dataclasses import dataclass

from dishka import Provider

from identity.infra.composition.action_provider import IdentityActionProvider
from identity.infra.composition.providers import IdentityProvider, IdentityTokenScopePolicy


@dataclass(frozen=True, slots=True)
class IdentityContainer:
    """Expose Identity's provider registrations and required runtime context."""

    token_scopes: tuple[str, ...]

    def providers(self) -> tuple[Provider, ...]:
        return (IdentityProvider(), IdentityActionProvider(component="identity_action"))

    def context(self) -> dict[type[object], object]:
        return {IdentityTokenScopePolicy: IdentityTokenScopePolicy(self.token_scopes)}

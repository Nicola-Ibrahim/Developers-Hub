"""Common enforcement used by the existing application dispatch boundaries."""

from collections.abc import Callable
from dataclasses import replace

from shared.authorization.interfaces import AuthorizationDecisionPort, AuthorizationUnavailable
from shared.authorization.models import AuthorizationDecision, AuthorizationRequest


def operation_id(message: object) -> str:
    message_type = message if isinstance(message, type) else type(message)
    return f"{message_type.__module__}.{message_type.__qualname__}"


async def require_authorized(
    authorizer: AuthorizationDecisionPort,
    message: object,
    facts: AuthorizationRequest,
    denied: Exception | Callable[[str | None], Exception],
) -> None:
    decision = await authorizer.evaluate(replace(facts, action=operation_id(message)))
    if not isinstance(decision, AuthorizationDecision) or type(decision.allowed) is not bool:
        raise AuthorizationUnavailable("Invalid authorization decision")
    if not decision.allowed:
        raise denied if isinstance(denied, Exception) else denied(decision.reason)

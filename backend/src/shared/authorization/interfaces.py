"""Application boundary for policy evaluation."""

from abc import ABC, abstractmethod

from shared.authorization.models import AuthorizationDecision, AuthorizationRequest


class AuthorizationDenied(Exception):
    def __init__(
        self, status: int = 403, code: str = "forbidden", message: str = "Permission denied"
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class AuthorizationUnavailable(Exception):
    """Policy decision could not be obtained or validated."""


class AuthorizationDecisionPort(ABC):
    @abstractmethod
    async def evaluate(self, request: AuthorizationRequest) -> AuthorizationDecision: ...

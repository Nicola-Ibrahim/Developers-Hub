"""API token eligibility and authenticated principal."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: UUID
    project_id: UUID
    token_id: UUID
    role: Literal["developer", "admin"]
    scopes: frozenset[str]


@dataclass(frozen=True)
class ApiTokenAuthenticationDetails:
    token_id: UUID
    user_id: UUID
    project_id: UUID
    role: str | None
    scopes: tuple[str, ...]
    user_active: bool
    expires_at: datetime
    revoked_at: datetime | None

"""Credentials supplied by a transport and revalidated by protected operations."""

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class SessionCredentials:
    session_token: str | None = field(repr=False)
    project_id: UUID | None = None
    csrf_token: str | None = field(default=None, repr=False)
    mutate: bool = False


@dataclass
class RequestCredentials:
    identity: str | SessionCredentials | None = field(default=None, repr=False)

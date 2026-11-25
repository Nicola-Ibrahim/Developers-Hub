"""Identity dispatcher messages for personal token management."""

from dataclasses import dataclass, field
from uuid import UUID

from identity.domain.records import PersonalApiToken
from shared.dispatch import Command, Query


@dataclass(frozen=True, slots=True)
class ListPersonalTokensQuery(Query[tuple[PersonalApiToken, ...]]):
    session_token: str = field(repr=False)
    project_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CreatePersonalTokenCommand(Command[tuple[PersonalApiToken, str]]):
    session_token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    origin: str | None
    name: str
    scopes: tuple[str, ...]
    hours: int


@dataclass(frozen=True, slots=True)
class RotatePersonalTokenCommand(Command[tuple[PersonalApiToken, str] | None]):
    session_token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    origin: str | None
    token_id: UUID


@dataclass(frozen=True, slots=True)
class RevokePersonalTokenCommand(Command[bool]):
    session_token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    origin: str | None
    token_id: UUID

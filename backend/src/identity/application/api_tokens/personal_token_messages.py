"""Identity dispatcher messages for personal token management."""

from dataclasses import dataclass
from uuid import UUID

from identity.domain.records import PersonalApiToken
from shared.dispatch import Command, Query


@dataclass(frozen=True, slots=True)
class ListPersonalTokensQuery(Query[tuple[PersonalApiToken, ...]]):
    actor_id: UUID
    project_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CreatePersonalTokenCommand(Command[tuple[PersonalApiToken, str]]):
    actor_id: UUID
    project_id: UUID | None
    name: str
    scopes: tuple[str, ...]
    hours: int


@dataclass(frozen=True, slots=True)
class RotatePersonalTokenCommand(Command[tuple[PersonalApiToken, str] | None]):
    actor_id: UUID
    token_id: UUID


@dataclass(frozen=True, slots=True)
class RevokePersonalTokenCommand(Command[bool]):
    actor_id: UUID
    token_id: UUID

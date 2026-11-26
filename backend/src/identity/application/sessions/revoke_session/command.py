from dataclasses import dataclass
from uuid import UUID

from shared.dispatch import Command


@dataclass(frozen=True, slots=True)
class RevokeSessionCommand(Command[bool]):
    actor_id: UUID
    session_id: UUID

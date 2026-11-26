from dataclasses import dataclass
from uuid import UUID

from shared.dispatch import Command


@dataclass(frozen=True, slots=True)
class RevokeAllSessionsCommand(Command[int]):
    actor_id: UUID

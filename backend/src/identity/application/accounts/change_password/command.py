from dataclasses import dataclass, field
from uuid import UUID

from shared.dispatch import Command


@dataclass(frozen=True, slots=True)
class ChangePasswordCommand(Command[None]):
    actor_id: UUID
    actor_name: str
    current_password: str = field(repr=False)
    new_password: str = field(repr=False)

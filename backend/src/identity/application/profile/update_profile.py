from dataclasses import dataclass
from uuid import UUID

from identity.domain.records import AccountProfile
from shared.dispatch import Command


@dataclass(frozen=True, slots=True)
class UpdateProfileCommand(Command[AccountProfile]):
    actor_id: UUID
    display_name: str | None

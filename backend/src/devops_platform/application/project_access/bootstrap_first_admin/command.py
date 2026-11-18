from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from shared.dispatch import Command


@dataclass(frozen=True, slots=True)
class BootstrapFirstAdmin(Command[None]):
    user_id: UUID
    project_id: UUID
    now: datetime

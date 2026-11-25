from dataclasses import dataclass, field

from identity.domain.records import AccountProfile
from shared.dispatch import Command


@dataclass(frozen=True, slots=True)
class UpdateProfileCommand(Command[AccountProfile]):
    session_token: str = field(repr=False)
    display_name: str | None
    csrf_token: str = field(repr=False)
    origin: str | None

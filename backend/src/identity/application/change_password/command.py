from dataclasses import dataclass, field

from shared.dispatch import Command


@dataclass(frozen=True, slots=True)
class ChangePasswordCommand(Command[None]):
    session_token: str = field(repr=False)
    current_password: str = field(repr=False)
    new_password: str = field(repr=False)
    csrf_token: str = field(repr=False)
    origin: str | None

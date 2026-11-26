from dataclasses import dataclass, field

from shared.dispatch import Command


@dataclass(frozen=True, slots=True)
class LogoutCommand(Command[None]):
    session_token: str = field(repr=False)

from dataclasses import dataclass, field
from uuid import UUID

from identity.application.authentication.login.result import LoginResult
from shared.dispatch import Command


@dataclass(frozen=True, slots=True)
class LoginCommand(Command[LoginResult]):
    user_name: str
    password: str = field(repr=False)
    project_id: UUID | None
    origin: str | None

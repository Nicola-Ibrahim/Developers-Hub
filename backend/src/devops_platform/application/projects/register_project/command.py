import re

from pydantic import BaseModel, ConfigDict, model_validator

from devops_platform.application.shared.errors import PlatformRequestError


class RegisterProjectCommand(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    name: str
    owning_team: str
    repository: str
    environments: tuple[str, ...]

    @model_validator(mode="after")
    def _validate(self) -> "RegisterProjectCommand":
        if (
            not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", self.name)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", self.owning_team)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository)
            or len(self.repository) > 200
            or not 1 <= len(self.environments) <= 20
            or len(set(self.environments)) != len(self.environments)
            or any(not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name) for name in self.environments)
        ):
            raise PlatformRequestError("invalid_registration", "Invalid project registration", 422)
        return self

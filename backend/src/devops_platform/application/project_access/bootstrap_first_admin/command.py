from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.dispatch import Command


class BootstrapFirstAdmin(BaseModel, Command[None]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    user_id: UUID
    project_id: UUID
    now: datetime

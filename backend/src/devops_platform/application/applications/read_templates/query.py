from pydantic import BaseModel, ConfigDict

from devops_platform.application.software_delivery.shared.models import TemplateVersion
from shared.dispatch import Query


class ReadTemplates(BaseModel, Query[tuple[TemplateVersion, ...]]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

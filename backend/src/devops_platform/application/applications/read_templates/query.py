from dataclasses import dataclass

from devops_platform.application.software_delivery.shared.models import TemplateVersion
from shared.dispatch import Query


@dataclass(frozen=True, slots=True)
class ReadTemplates(Query[tuple[TemplateVersion, ...]]):
    pass

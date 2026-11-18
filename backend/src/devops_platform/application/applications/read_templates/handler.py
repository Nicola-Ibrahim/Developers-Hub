"""Read the approved application template catalog."""

from devops_platform.application.applications.read_templates.query import ReadTemplates
from devops_platform.application.interfaces.software_delivery import TemplateCatalog
from devops_platform.application.software_delivery.shared.models import TemplateVersion


class ReadTemplatesHandler:
    def __init__(self, templates: TemplateCatalog) -> None:
        self.templates = templates

    async def execute(self, query: ReadTemplates) -> tuple[TemplateVersion, ...]:
        del query
        return self.templates.list_templates()

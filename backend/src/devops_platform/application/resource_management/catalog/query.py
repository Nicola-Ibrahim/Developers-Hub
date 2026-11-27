from pydantic import BaseModel, ConfigDict

from devops_platform.application.shared.dto import AccessContext, CatalogResult
from shared.dispatch import Query


class ReadCatalog(BaseModel, Query[CatalogResult]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    access: AccessContext

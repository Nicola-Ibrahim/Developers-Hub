# ruff: noqa: F401
"""Safe local adapters for approved templates and explicitly configured providers."""

import base64
import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID

from devops_platform.application.interfaces.software_delivery import (
    ApplicationDeliveryFailure,
    ApprovedImageCatalog,
    RequestFingerprint,
    TemplateCatalog,
    WebhookSignatureVerifier,
)
from devops_platform.application.software_delivery.shared.models import (
    GeneratedFile,
    TemplateVersion,
)


class Sha256RequestFingerprint(RequestFingerprint):
    """Stable request identity encoding for idempotency conflict checks."""

    def for_value(self, value: object) -> str:
        payload = json.dumps(value.__dict__, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

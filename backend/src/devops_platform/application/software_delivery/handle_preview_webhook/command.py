from dataclasses import dataclass, field
from datetime import datetime

from devops_platform.application.software_delivery.shared.models import WebhookResult
from shared.dispatch import Command


@dataclass(frozen=True, slots=True)
class ProcessGithubPreviewWebhook(Command[WebhookResult]):
    raw_body: bytes = field(repr=False)
    signature: str | None = field(repr=False)
    delivery_id: str | None
    event: str | None
    now: datetime

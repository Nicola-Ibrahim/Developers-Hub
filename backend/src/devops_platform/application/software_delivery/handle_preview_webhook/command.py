import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from devops_platform.application.shared.errors import PlatformRequestError
from devops_platform.application.software_delivery.shared.models import WebhookResult
from devops_platform.application.software_delivery.shared.policy import DIGEST
from shared.dispatch import Command

_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")


class ProcessGithubPreviewWebhook(BaseModel, Command[WebhookResult]):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", hide_input_in_errors=True)

    raw_body: bytes = Field(repr=False)
    signature: str | None = Field(repr=False)
    delivery_id: str | None
    event: str | None
    now: datetime

    def require_headers(self) -> tuple[str, str]:
        delivery_id, event = self.delivery_id, self.event
        if delivery_id is None or event is None:
            raise PlatformRequestError(
                "webhook_invalid", "GitHub delivery headers are required", 400
            )
        return delivery_id, event

    def validate_envelope(self, delivery_id: str) -> None:
        if len(self.raw_body) > 1024 * 1024 or not re.fullmatch(
            r"[A-Fa-f0-9-]{16,100}", delivery_id
        ):
            raise PlatformRequestError("webhook_invalid", "Webhook envelope is invalid", 400)

    def read_event(self, payload: dict[str, object]) -> tuple[str, str, dict[str, object]]:
        action = payload.get("action")
        repository_data = payload.get("repository")
        pull_request = payload.get("pull_request")
        if (
            self.event != "pull_request"
            or not isinstance(action, str)
            or action not in {"opened", "reopened", "synchronize", "closed"}
            or not isinstance(repository_data, dict)
            or not isinstance(pull_request, dict)
        ):
            raise PlatformRequestError("webhook_invalid", "Unsupported GitHub event", 400)
        repository = repository_data.get("full_name")
        if (
            not isinstance(repository, str)
            or not _REPOSITORY.fullmatch(repository)
            or ".." in repository
        ):
            raise PlatformRequestError("webhook_invalid", "Repository identity is invalid", 400)
        return action, repository, pull_request

    @staticmethod
    def read_number(pull_request: dict[str, object]) -> int:
        number = pull_request.get("number")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise PlatformRequestError("webhook_invalid", "Pull request identity is invalid", 400)
        return number

    @staticmethod
    def read_preview_head(
        pull_request: dict[str, object], repository: str
    ) -> dict[str, object] | WebhookResult:
        head = pull_request.get("head")
        base = pull_request.get("base")
        if not isinstance(head, dict) or not isinstance(base, dict):
            return WebhookResult(False, False, None, reason="pull_request_head_missing")
        head_repo = head.get("repo")
        base_repo = base.get("repo")
        if not isinstance(head_repo, dict) or not isinstance(base_repo, dict):
            return WebhookResult(False, False, None, reason="pull_request_repo_missing")
        head_full_name, base_full_name = head_repo.get("full_name"), base_repo.get("full_name")
        if (
            not isinstance(head_full_name, str)
            or head_full_name.casefold() != repository.casefold()
        ):
            return WebhookResult(False, False, None, reason="untrusted_fork")
        if (
            not isinstance(base_full_name, str)
            or base_full_name.casefold() != repository.casefold()
        ):
            return WebhookResult(False, False, None, reason="pull_request_base_mismatch")
        return head

    @staticmethod
    def read_preview_source(
        head: dict[str, object], pull_request: dict[str, object]
    ) -> tuple[str, str, str | None] | WebhookResult:
        head_sha, branch = head.get("sha"), head.get("ref")
        if (
            not isinstance(head_sha, str)
            or not re.fullmatch(r"[a-f0-9]{40}", head_sha)
            or not isinstance(branch, str)
            or len(branch) > 255
            or ".." in branch
        ):
            return WebhookResult(False, False, None, reason="untrusted_head_reference")
        image_digest = pull_request.get("platform_image_digest")
        if image_digest is not None and (
            not isinstance(image_digest, str) or not DIGEST.fullmatch(image_digest)
        ):
            return WebhookResult(False, False, None, reason="preview_image_not_approved")
        return head_sha, branch, image_digest

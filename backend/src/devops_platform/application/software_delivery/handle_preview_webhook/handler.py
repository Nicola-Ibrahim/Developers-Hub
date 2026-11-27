"""Validate and record approved GitHub pull-request preview events."""

from uuid import UUID

from devops_platform.application.interfaces.software_delivery import (
    ApprovedImageCatalog,
    PreviewWebhookRepository,
    WebhookSignatureVerifier,
)
from devops_platform.application.shared.errors import PlatformRequestError
from devops_platform.application.software_delivery.handle_preview_webhook.command import (
    ProcessGithubPreviewWebhook,
)
from devops_platform.application.software_delivery.shared.models import WebhookResult


class ProcessGithubPreviewWebhookHandler:
    def __init__(
        self,
        repository: PreviewWebhookRepository,
        images: ApprovedImageCatalog,
        webhook_verifier: WebhookSignatureVerifier | None,
        allowed_repository_owner: str | None,
        preview_owner_id: UUID | None,
        preview_ttl_seconds: int,
    ) -> None:
        self.repository = repository
        self.images = images
        self.webhook_verifier = webhook_verifier
        self.allowed_repository_owner = allowed_repository_owner
        self.preview_owner_id = preview_owner_id
        self.preview_ttl_seconds = preview_ttl_seconds

    def verify_signature(
        self, command: ProcessGithubPreviewWebhook
    ) -> tuple[dict[str, object], str]:
        delivery_id, _ = command.require_headers()
        if self.webhook_verifier is None or self.allowed_repository_owner is None:
            raise PlatformRequestError(
                "webhooks_disabled", "GitHub preview events are not configured", 503
            )
        command.validate_envelope(delivery_id)
        return self.webhook_verifier.verify(command.raw_body, command.signature)

    async def execute(self, command: ProcessGithubPreviewWebhook) -> WebhookResult:
        return await self.execute_verified(command, self.verify_signature(command))

    async def execute_verified(
        self,
        command: ProcessGithubPreviewWebhook,
        verified: tuple[dict[str, object], str],
    ) -> WebhookResult:
        payload, payload_hash = verified
        delivery_id, event = command.require_headers()
        allowed_repository_owner = self.allowed_repository_owner
        if allowed_repository_owner is None:
            raise PlatformRequestError(
                "webhooks_disabled", "GitHub preview events are not configured", 503
            )
        action, repository, pull_request = command.read_event(payload)
        owner, _ = repository.split("/", 1)
        if owner.casefold() != allowed_repository_owner.casefold():
            raise PlatformRequestError("webhook_forbidden", "Repository is not approved", 403)
        number = command.read_number(pull_request)
        recorded = await self.repository.record_webhook(
            delivery_id=delivery_id,
            payload_hash=payload_hash,
            event=event,
            repository=repository.casefold(),
            pull_request=number,
            action=action,
            now=command.now,
        )
        if not recorded:
            return WebhookResult(True, True, None, reason="duplicate_delivery")
        if action == "closed":
            count = await self.repository.close_preview(
                repository=repository.casefold(), pull_request=number, now=command.now
            )
            return WebhookResult(True, False, None, cleanup_count=count)
        registered = await self.repository.find_registered_repository(repository.casefold())
        if registered is None:
            return WebhookResult(False, False, None, reason="repository_not_registered")
        head = command.read_preview_head(pull_request, repository)
        if isinstance(head, WebhookResult):
            return head
        if self.preview_owner_id is None:
            return WebhookResult(False, False, None, reason="preview_owner_not_configured")
        source = command.read_preview_source(head, pull_request)
        if isinstance(source, WebhookResult):
            return source
        head_sha, branch, image_digest = source
        if image_digest is not None and not self.images.is_approved(image_digest, "local"):
            return WebhookResult(False, False, None, reason="preview_image_not_approved")
        application_id = await self.repository.request_preview(
            project_id=registered.project_id,
            owner_id=self.preview_owner_id,
            repository=repository.casefold(),
            pull_request=number,
            branch=branch,
            head_sha=head_sha,
            image_digest=image_digest,
            template_id="python-fastapi",
            template_version="1.0.0",
            ttl_seconds=self.preview_ttl_seconds,
            now=command.now,
        )
        return WebhookResult(True, False, application_id)

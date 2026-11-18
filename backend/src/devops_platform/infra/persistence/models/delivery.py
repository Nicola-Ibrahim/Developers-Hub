"""SQLAlchemy table mappings for application delivery."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.infra.persistence.base import Base, utc_now


class ApplicationRow(Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','ready','failed','deleting','deleted')", name="status"
        ),
        UniqueConstraint("project_id", "name", name="uq_application_project_name"),
        Index("ix_applications_project_updated", "project_id", "updated_at"),
        Index("ix_applications_preview", "source_repository", "pull_request"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("project_registrations.project_id"))
    environment_id: Mapped[UUID] = mapped_column(ForeignKey("project_environments.id"))
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(64))
    template_id: Mapped[str] = mapped_column(String(64))
    template_version: Mapped[str] = mapped_column(String(32))
    repository_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resource_id: Mapped[UUID | None] = mapped_column(ForeignKey("resources.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    is_preview: Mapped[bool] = mapped_column(Boolean, default=False)
    source_repository: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pull_request: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ApplicationDeliveryStepRow(Base):
    __tablename__ = "application_delivery_steps"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('repository','resource','deployment','template_update','preview_cleanup')",
            name="kind",
        ),
        CheckConstraint("status IN ('pending','running','succeeded','failed')", name="status"),
        CheckConstraint("attempts >= 0", name="attempts"),
        UniqueConstraint("idempotency_key", name="uq_application_delivery_step_key"),
        Index("ix_application_delivery_due", "status", "next_attempt_at", "claim_expires_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(200))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    claim_token: Mapped[UUID | None]
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ApplicationDeliveryIdempotencyRow(Base):
    __tablename__ = "application_delivery_idempotency"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", "route", "key", name="uq_app_delivery_scope"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    project_id: Mapped[UUID] = mapped_column(ForeignKey("project_registrations.project_id"))
    route: Mapped[str] = mapped_column(String(100))
    key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    application_id: Mapped[UUID] = mapped_column(ForeignKey("applications.id"))
    result_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ApplicationDeploymentRow(Base):
    __tablename__ = "application_deployments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed','deleted')", name="status"
        ),
        Index("ix_application_deployments_history", "application_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    requested_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    image_digest: Mapped[str] = mapped_column(String(300))
    target_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApplicationWebhookEventRow(Base):
    __tablename__ = "application_webhook_events"

    delivery_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    event: Mapped[str] = mapped_column(String(80))
    repository: Mapped[str] = mapped_column(String(200))
    pull_request: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(40))
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

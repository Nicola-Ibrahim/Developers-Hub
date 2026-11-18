"""Identity activity table mappings."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from shared.infra.persistence.base import Base, utc_now


class IdentityActivityRow(Base):
    __tablename__ = "identity_activity"
    __table_args__ = (Index("ix_identity_activity_time", "subject_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    subject_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    outcome: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

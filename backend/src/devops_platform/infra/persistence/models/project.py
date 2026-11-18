"""SQLAlchemy table mappings for project configuration."""

from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from shared.infra.persistence.base import Base


class ProjectRegistrationRow(Base):
    __tablename__ = "project_registrations"

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    owning_team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"))
    owning_team_name: Mapped[str | None] = mapped_column(String(100))
    repository: Mapped[str | None] = mapped_column(String(200))
    configured: Mapped[bool] = mapped_column(Boolean, default=False)


class ProjectEnvironmentRow(Base):
    __tablename__ = "project_environments"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_project_environment"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("project_registrations.project_id"))
    name: Mapped[str] = mapped_column(String(64))

"""Add self-service profile display name.

Revision ID: 0002_identity_profile
Revises: 0001_initial_schema
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_identity_profile"
down_revision: str | Sequence[str] | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "display_name")

"""Add names to API tokens for personal token management."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_personal_tokens"
down_revision: str | Sequence[str] | None = "0002_identity_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("api_tokens", sa.Column("name", sa.String(length=100), nullable=True))
    op.execute("UPDATE api_tokens SET name = 'Legacy token' WHERE name IS NULL")
    op.alter_column("api_tokens", "name", nullable=False, server_default="Legacy token")


def downgrade() -> None:
    op.drop_column("api_tokens", "name")

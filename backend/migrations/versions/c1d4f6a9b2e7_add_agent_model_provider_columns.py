"""add model provider/name to agents

Revision ID: c1d4f6a9b2e7
Revises: a9b1c2d3e4f7
Create Date: 2026-04-07 17:30:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c1d4f6a9b2e7"
down_revision = "a9b1c2d3e4f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("model_provider", sa.String(length=64), nullable=False, server_default="openai"),
    )
    op.add_column("agents", sa.Column("model_name", sa.String(length=255), nullable=True))
    op.execute("UPDATE agents SET model_provider = 'openai' WHERE model_provider IS NULL")
    op.alter_column("agents", "model_provider", server_default=None)
    op.create_index(op.f("ix_agents_model_provider"), "agents", ["model_provider"], unique=False)
    op.create_index(op.f("ix_agents_model_name"), "agents", ["model_name"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agents_model_name"), table_name="agents")
    op.drop_index(op.f("ix_agents_model_provider"), table_name="agents")
    op.drop_column("agents", "model_name")
    op.drop_column("agents", "model_provider")

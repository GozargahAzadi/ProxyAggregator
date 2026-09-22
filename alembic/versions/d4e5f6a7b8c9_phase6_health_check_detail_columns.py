"""phase6 health check detail columns

Revision ID: d4e5f6a7b8c9
Revises: c2f13f33da92
Create Date: 2026-09-22 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c2f13f33da92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Record the working IP used for a proxy's most recent successful check.
    op.add_column("proxy_configs", sa.Column("working_ip", sa.String(length=45), nullable=True))

    # Rich, structured health check results from the Phase 6 runner.
    op.add_column("health_checks", sa.Column("status", sa.String(length=32), nullable=True))
    op.add_column("health_checks", sa.Column("checked_ip", sa.String(length=45), nullable=True))
    op.add_column("health_checks", sa.Column("attempted_ips", sa.Text(), nullable=True))
    op.add_column("health_checks", sa.Column("connect_ms", sa.Float(), nullable=True))
    op.add_column("health_checks", sa.Column("tls_ms", sa.Float(), nullable=True))
    op.add_column("health_checks", sa.Column("proxy_ms", sa.Float(), nullable=True))
    op.add_column(
        "health_checks",
        sa.Column("tls_used", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "health_checks",
        sa.Column("protocol_checked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("health_checks", "protocol_checked")
    op.drop_column("health_checks", "tls_used")
    op.drop_column("health_checks", "proxy_ms")
    op.drop_column("health_checks", "tls_ms")
    op.drop_column("health_checks", "connect_ms")
    op.drop_column("health_checks", "attempted_ips")
    op.drop_column("health_checks", "checked_ip")
    op.drop_column("health_checks", "status")

    op.drop_column("proxy_configs", "working_ip")

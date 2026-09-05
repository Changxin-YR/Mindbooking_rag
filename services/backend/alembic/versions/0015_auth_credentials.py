"""Persist password credentials and revocable session metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_auth_credentials"
down_revision: str | None = "0014_risk_center"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_password_credentials",
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("account_id"),
        sa.ForeignKeyConstraint(["account_id"], ["platform_accounts.id"]),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("token_fingerprint", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["platform_accounts.id"]),
        sa.UniqueConstraint("token_fingerprint", name="uq_auth_sessions_token_fingerprint"),
    )
    op.create_index(
        "ix_auth_sessions_account_expires",
        "auth_sessions",
        ["account_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_account_expires", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("account_password_credentials")

"""Add durable Staff credential, session, device, MFA, and role records."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_staff_auth_rbac"
down_revision: str | None = "0016_wallet_lot_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )


def upgrade() -> None:
    op.create_table(
        "staff_credentials",
        sa.Column("staff_id", sa.String(36), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("staff_id"),
        sa.ForeignKeyConstraint(["staff_id"], ["staff_accounts.id"]),
    )
    op.create_table(
        "staff_sessions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("staff_id", sa.String(36), nullable=False),
        sa.Column("token_fingerprint", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["staff_id"], ["staff_accounts.id"]),
        sa.UniqueConstraint("token_fingerprint", name="uq_staff_sessions_token_fingerprint"),
    )
    op.create_index("ix_staff_sessions_staff_expires", "staff_sessions", ["staff_id", "expires_at"])
    op.create_table(
        "staff_devices",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("staff_id", sa.String(36), nullable=False),
        sa.Column("device_fingerprint", sa.String(128), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["staff_id"], ["staff_accounts.id"]),
        sa.UniqueConstraint("staff_id", "device_fingerprint", name="uq_staff_device_fingerprint"),
    )
    op.create_table(
        "staff_mfa_factors",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("staff_id", sa.String(36), nullable=False),
        sa.Column("factor_type", sa.String(32), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["staff_id"], ["staff_accounts.id"]),
    )
    op.create_table(
        "staff_roles",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_staff_role_name"),
    )
    op.create_table(
        "staff_role_bindings",
        sa.Column("staff_id", sa.String(36), nullable=False),
        sa.Column("role_id", sa.String(36), nullable=False),
        sa.PrimaryKeyConstraint("staff_id", "role_id"),
        sa.ForeignKeyConstraint(["staff_id"], ["staff_accounts.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["staff_roles.id"]),
    )
    op.create_table(
        "staff_role_permissions",
        sa.Column("role_id", sa.String(36), nullable=False),
        sa.Column("permission", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("role_id", "permission"),
        sa.ForeignKeyConstraint(["role_id"], ["staff_roles.id"]),
    )


def downgrade() -> None:
    for table in (
        "staff_role_permissions",
        "staff_role_bindings",
        "staff_roles",
        "staff_mfa_factors",
        "staff_devices",
        "staff_sessions",
        "staff_credentials",
    ):
        op.drop_table(table)

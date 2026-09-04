"""Create identity, author, and staff/RBAC foundations."""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0002_identity_author_staff"
down_revision: str | None = "0001_foundation"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("identity_type", sa.String(32), nullable=False),
        sa.Column("normalized_value", sa.String(255), nullable=False),
        sa.UniqueConstraint("identity_type", "normalized_value", name="uq_login_identity_value"),
    )
    op.create_table(
        "platform_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
    )
    op.create_table(
        "login_identity_accounts",
        sa.Column("identity_id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.PrimaryKeyConstraint("identity_id", "account_id"),
        sa.ForeignKeyConstraint(["identity_id"], ["login_identities.id"]),
        sa.ForeignKeyConstraint(["account_id"], ["platform_accounts.id"]),
    )
    op.create_table(
        "login_identity_routing",
        sa.Column("identity_id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.ForeignKeyConstraint(["identity_id"], ["login_identities.id"]),
        sa.ForeignKeyConstraint(["account_id"], ["platform_accounts.id"]),
    )
    op.create_table(
        "real_name_subjects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("id_fingerprint", sa.String(64), nullable=False),
        sa.Column("encrypted_name", sa.Text(), nullable=False),
        sa.Column("encrypted_id_number", sa.Text(), nullable=False),
        sa.UniqueConstraint("id_fingerprint", name="uq_real_name_subject_fingerprint"),
    )
    op.create_table(
        "account_real_name_links",
        sa.Column("account_id", sa.String(36), primary_key=True),
        sa.Column("real_name_subject_id", sa.String(36), nullable=False),
        sa.Column("slot_status", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "slot_status IN ('ACTIVE', 'PENDING_RELEASE', 'RELEASED', 'BLOCKED_BY_VIOLATION')",
            name="ck_real_name_slot_status",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["platform_accounts.id"]),
        sa.ForeignKeyConstraint(["real_name_subject_id"], ["real_name_subjects.id"]),
    )
    op.create_table(
        "author_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("pen_name", sa.String(255), nullable=False),
        sa.Column("normalized_pen_name", sa.String(255), nullable=False),
        sa.UniqueConstraint("account_id", name="uq_author_profile_account"),
    )
    op.create_table(
        "author_pen_name_registry",
        sa.Column("normalized_pen_name", sa.String(255), primary_key=True),
        sa.Column("author_profile_id", sa.String(36), nullable=False),
        sa.ForeignKeyConstraint(["author_profile_id"], ["author_profiles.id"]),
    )
    op.create_table(
        "pen_name_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("author_profile_id", sa.String(36), nullable=False),
        sa.Column("pen_name", sa.String(255), nullable=False),
        sa.Column("normalized_pen_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["author_profile_id"], ["author_profiles.id"]),
        sa.UniqueConstraint("normalized_pen_name", name="uq_pen_name_history_normalized"),
    )
    op.create_table(
        "staff_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("employee_code", sa.String(128), nullable=False),
        sa.Column("department", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.UniqueConstraint("employee_code", name="uq_staff_employee_code"),
        sa.CheckConstraint(
            "status IN ('PENDING_ACTIVATION', 'ACTIVE', 'LOCKED', 'DISABLED', 'OFFBOARDED')",
            name="ck_staff_status",
        ),
    )
    op.create_table(
        "staff_permissions",
        sa.Column("staff_id", sa.String(36), nullable=False),
        sa.Column("permission", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("staff_id", "permission"),
        sa.ForeignKeyConstraint(["staff_id"], ["staff_accounts.id"]),
    )
    op.create_table(
        "staff_data_scopes",
        sa.Column("staff_id", sa.String(36), nullable=False),
        sa.Column("scope_type", sa.String(64), nullable=False),
        sa.Column("scope_value", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("staff_id", "scope_type", "scope_value"),
        sa.ForeignKeyConstraint(["staff_id"], ["staff_accounts.id"]),
    )


def downgrade() -> None:
    for table in (
        "staff_data_scopes",
        "staff_permissions",
        "staff_accounts",
        "pen_name_history",
        "author_pen_name_registry",
        "author_profiles",
        "account_real_name_links",
        "real_name_subjects",
        "login_identity_routing",
        "login_identity_accounts",
        "platform_accounts",
        "login_identities",
    ):
        op.drop_table(table)

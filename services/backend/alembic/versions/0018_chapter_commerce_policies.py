"""Persist chapter purchase pricing and access mode."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_chapter_commerce_policies"
down_revision: str | None = "0017_staff_auth_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chapter_commerce_policies",
        sa.Column("chapter_id", sa.String(64), nullable=False),
        sa.Column("price_coin", sa.BigInteger(), nullable=False),
        sa.Column("access_mode", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("chapter_id"),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"]),
        sa.CheckConstraint("price_coin > 0", name="ck_chapter_commerce_policies_price_positive"),
    )


def downgrade() -> None:
    op.drop_table("chapter_commerce_policies")

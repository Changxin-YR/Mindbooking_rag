"""Add reader discovery, social, growth, correction, and minor policy facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_reader_experience"
down_revision: str | None = "0009_operation_legal"
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
    op.add_column("book_metadata_versions", sa.Column("channel", sa.String(16), nullable=False, server_default="UNSPECIFIED"))
    op.add_column("book_metadata_versions", sa.Column("category", sa.String(64), nullable=False, server_default=""))
    op.add_column("book_metadata_versions", sa.Column("tags_json", sa.Text, nullable=False, server_default="[]"))
    op.create_table(
        "book_user_ratings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("overall_score", sa.SmallInteger, nullable=False),
        sa.Column("plot_score", sa.SmallInteger, nullable=False),
        sa.Column("character_score", sa.SmallInteger, nullable=False),
        sa.Column("writing_score", sa.SmallInteger, nullable=False),
        sa.Column("update_score", sa.SmallInteger, nullable=False),
        sa.Column("eligibility_metric_version", sa.String(64), nullable=False),
        sa.Column("eligible_words", sa.BigInteger, nullable=False),
        _created_at(),
        sa.UniqueConstraint("account_id", "book_id", name="uq_book_user_rating"),
        sa.CheckConstraint("overall_score BETWEEN 1 AND 5", name="ck_rating_overall"),
    )
    op.create_table(
        "book_user_rating_versions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("rating_id", sa.String(64), nullable=False),
        sa.Column("overall_score", sa.SmallInteger, nullable=False),
        sa.Column("plot_score", sa.SmallInteger, nullable=False),
        sa.Column("character_score", sa.SmallInteger, nullable=False),
        sa.Column("writing_score", sa.SmallInteger, nullable=False),
        sa.Column("update_score", sa.SmallInteger, nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["rating_id"], ["book_user_ratings.id"]),
    )
    op.create_table(
        "follow_relations",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        _created_at(),
        sa.UniqueConstraint("account_id", "target_type", "target_id", name="uq_follow_relation"),
        sa.CheckConstraint("target_type IN ('AUTHOR', 'ACCOUNT')", name="ck_follow_target_type"),
    )
    op.create_table(
        "user_growth_profiles",
        sa.Column("account_id", sa.String(64), primary_key=True),
        sa.Column("points", sa.BigInteger, nullable=False, server_default=sa.text("0")),
        sa.Column("level", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("membership_level", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("fan_level", sa.Integer, nullable=False, server_default=sa.text("0")),
        _created_at(),
    )
    op.create_table(
        "user_growth_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("points", sa.BigInteger, nullable=False),
        _created_at(),
        sa.CheckConstraint("points > 0", name="ck_growth_points_positive"),
    )
    op.create_table(
        "content_correction_reports",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("chapter_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("position", sa.BigInteger, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        _created_at(),
        sa.CheckConstraint("position >= 0", name="ck_correction_position"),
    )
    op.create_table(
        "minor_protection_profiles",
        sa.Column("account_id", sa.String(64), primary_key=True),
        sa.Column("is_minor", sa.Boolean, nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        _created_at(),
    )


def downgrade() -> None:
    for table in (
        "minor_protection_profiles",
        "content_correction_reports",
        "user_growth_events",
        "user_growth_profiles",
        "follow_relations",
        "book_user_rating_versions",
        "book_user_ratings",
    ):
        op.drop_table(table)
    op.drop_column("book_metadata_versions", "tags_json")
    op.drop_column("book_metadata_versions", "category")
    op.drop_column("book_metadata_versions", "channel")

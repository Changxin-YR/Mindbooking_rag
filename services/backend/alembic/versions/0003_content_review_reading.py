"""Add content, review, reading and library facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_content_review_reading"
down_revision: str | None = "0002_identity_author_staff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp() -> sa.Column[sa.DateTime]:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )


def upgrade() -> None:
    op.create_table(
        "books",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("lifecycle", sa.String(32), nullable=False),
        sa.Column("visibility", sa.String(32), nullable=False),
        sa.Column("public_metadata_version_id", sa.String(64), nullable=True),
        _timestamp(),
    )
    op.create_table(
        "book_metadata_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("book_id", sa.String(64), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("synopsis", sa.Text, nullable=False),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.false()),
        _timestamp(),
        sa.UniqueConstraint("book_id", "version", name="uq_book_metadata_version"),
    )
    op.create_table(
        "volumes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("book_id", sa.String(64), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        _timestamp(),
        sa.UniqueConstraint("book_id", "number", name="uq_volume_book_number"),
    )
    op.create_table(
        "chapters",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("volume_id", sa.String(64), sa.ForeignKey("volumes.id"), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("commercial_policy", sa.String(16), nullable=False),
        sa.Column("publish_state", sa.String(16), nullable=False),
        sa.Column("visibility_state", sa.String(32), nullable=False),
        sa.Column("published_version_id", sa.String(64), nullable=True),
        _timestamp(),
        sa.UniqueConstraint("volume_id", "number", name="uq_chapter_volume_number"),
    )
    op.create_table(
        "chapter_draft_heads",
        sa.Column("chapter_id", sa.String(64), sa.ForeignKey("chapters.id"), primary_key=True),
        sa.Column("current_revision", sa.Integer, nullable=False, server_default="0"),
        sa.Column("current_snapshot_id", sa.String(64), nullable=True),
        _timestamp(),
    )
    op.create_table(
        "chapter_draft_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("chapter_id", sa.String(64), sa.ForeignKey("chapters.id"), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("save_mode", sa.String(16), nullable=False),
        _timestamp(),
        sa.UniqueConstraint("chapter_id", "revision", name="uq_draft_snapshot_revision"),
    )
    op.create_table(
        "chapter_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("chapter_id", sa.String(64), sa.ForeignKey("chapters.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column(
            "snapshot_id",
            sa.String(64),
            sa.ForeignKey("chapter_draft_snapshots.id"),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("word_count", sa.Integer, nullable=False),
        _timestamp(),
        sa.UniqueConstraint("chapter_id", "version", name="uq_chapter_version"),
    )
    op.create_table(
        "review_submissions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("book_id", sa.String(64), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("submission_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        _timestamp(),
    )
    op.create_table(
        "review_submission_versions",
        sa.Column(
            "submission_id", sa.String(64), sa.ForeignKey("review_submissions.id"), nullable=False
        ),
        sa.Column(
            "chapter_version_id",
            sa.String(64),
            sa.ForeignKey("chapter_versions.id"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint("submission_id", "chapter_version_id"),
        sa.UniqueConstraint("submission_id", "position", name="uq_submission_version_position"),
    )
    op.create_table(
        "review_tasks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "submission_id", sa.String(64), sa.ForeignKey("review_submissions.id"), nullable=False
        ),
        sa.Column("task_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        _timestamp(),
    )
    op.create_table(
        "review_decisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "submission_id", sa.String(64), sa.ForeignKey("review_submissions.id"), nullable=False
        ),
        sa.Column("reviewer_id", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        _timestamp(),
    )
    op.create_table(
        "book_reading_progress",
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("last_chapter_id", sa.String(64), nullable=True),
        sa.Column("last_chapter_number", sa.Integer, nullable=False),
        sa.Column("last_position", sa.Integer, nullable=False),
        sa.Column("furthest_chapter_id", sa.String(64), nullable=True),
        sa.Column("furthest_chapter_number", sa.Integer, nullable=False),
        sa.Column("furthest_position", sa.Integer, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("current_session_id", sa.String(128), nullable=True),
        _timestamp(),
        sa.PrimaryKeyConstraint("account_id", "book_id"),
    )
    op.create_table(
        "bookshelf_entries",
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("group_name", sa.String(64), nullable=False),
        _timestamp(),
        sa.PrimaryKeyConstraint("account_id", "book_id"),
    )


def downgrade() -> None:
    op.drop_table("bookshelf_entries")
    op.drop_table("book_reading_progress")
    op.drop_table("review_decisions")
    op.drop_table("review_tasks")
    op.drop_table("review_submission_versions")
    op.drop_table("review_submissions")
    op.drop_table("chapter_versions")
    op.drop_table("chapter_draft_snapshots")
    op.drop_table("chapter_draft_heads")
    op.drop_table("chapters")
    op.drop_table("volumes")
    op.drop_table("book_metadata_versions")
    op.drop_table("books")

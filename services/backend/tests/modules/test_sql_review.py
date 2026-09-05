import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine

from novel_platform.modules.content.domain import BookVisibility, CommercialPolicy
from novel_platform.modules.content.sql_service import SqlContentService
from novel_platform.modules.review.domain import ReviewDecision, ReviewSubmissionStatus
from novel_platform.modules.review.sql_service import SqlReviewService


def _schema() -> sa.MetaData:
    metadata = sa.MetaData()
    books = sa.Table(
        "books",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("lifecycle", sa.String(32), nullable=False),
        sa.Column("visibility", sa.String(32), nullable=False),
        sa.Column("public_metadata_version_id", sa.String(64)),
    )
    sa.Table(
        "book_metadata_versions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("book_id", sa.String(64), sa.ForeignKey(books.c.id), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("synopsis", sa.Text, nullable=False),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("channel", sa.String(16), nullable=False, server_default="UNSPECIFIED"),
        sa.Column("category", sa.String(64), nullable=False, server_default=""),
        sa.Column("tags_json", sa.Text, nullable=False, server_default="[]"),
        sa.UniqueConstraint("book_id", "version"),
    )
    volumes = sa.Table(
        "volumes",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("book_id", sa.String(64), sa.ForeignKey(books.c.id), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.UniqueConstraint("book_id", "number"),
    )
    chapters = sa.Table(
        "chapters",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("volume_id", sa.String(64), sa.ForeignKey(volumes.c.id), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("commercial_policy", sa.String(16), nullable=False),
        sa.Column("publish_state", sa.String(16), nullable=False),
        sa.Column("visibility_state", sa.String(32), nullable=False),
        sa.Column("published_version_id", sa.String(64)),
        sa.UniqueConstraint("volume_id", "number"),
    )
    sa.Table(
        "chapter_draft_heads",
        metadata,
        sa.Column("chapter_id", sa.String(64), sa.ForeignKey(chapters.c.id), primary_key=True),
        sa.Column("current_revision", sa.Integer, nullable=False, server_default="0"),
        sa.Column("current_snapshot_id", sa.String(64)),
    )
    snapshots = sa.Table(
        "chapter_draft_snapshots",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("chapter_id", sa.String(64), sa.ForeignKey(chapters.c.id), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("save_mode", sa.String(16), nullable=False),
        sa.UniqueConstraint("chapter_id", "revision"),
    )
    versions = sa.Table(
        "chapter_versions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("chapter_id", sa.String(64), sa.ForeignKey(chapters.c.id), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("snapshot_id", sa.String(64), sa.ForeignKey(snapshots.c.id), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("word_count", sa.Integer, nullable=False),
        sa.UniqueConstraint("chapter_id", "version"),
    )
    submissions = sa.Table(
        "review_submissions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("book_id", sa.String(64), sa.ForeignKey(books.c.id), nullable=False),
        sa.Column("submission_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
    )
    sa.Table(
        "review_submission_versions",
        metadata,
        sa.Column(
            "submission_id", sa.String(64), sa.ForeignKey(submissions.c.id), primary_key=True
        ),
        sa.Column(
            "chapter_version_id", sa.String(64), sa.ForeignKey(versions.c.id), primary_key=True
        ),
        sa.Column("position", sa.Integer, nullable=False),
        sa.UniqueConstraint("submission_id", "position"),
    )
    sa.Table(
        "review_tasks",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("submission_id", sa.String(64), sa.ForeignKey(submissions.c.id), nullable=False),
        sa.Column("task_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("assigned_staff_id", sa.String(64)),
    )
    sa.Table(
        "review_decisions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("submission_id", sa.String(64), sa.ForeignKey(submissions.c.id), nullable=False),
        sa.Column("reviewer_id", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    return metadata


def _review() -> tuple[SqlReviewService, SqlContentService]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _schema().create_all(engine)
    content = SqlContentService(engine)
    return SqlReviewService(engine, content), content


def _fixed_version(content: SqlContentService, title: str = "Book") -> tuple[object, object]:
    book = content.create_book("author-1", title)
    volume = content.create_volume(book.id, "Volume 1", 1)
    chapter = content.create_chapter(volume.id, "Chapter 1", CommercialPolicy.FREE)
    version = content.create_chapter_version(chapter.id, content.save_draft(chapter.id, "fixed").id)
    return book, version


def test_sql_review_submission_and_approval_survive_service_rebuild() -> None:
    review, content = _review()
    book, version = _fixed_version(content)

    submission = review.submit_first_listing(book.id, [version.id])

    assert submission.fixed_version_ids == (version.id,)
    assert content.get_book(book.id).visibility is BookVisibility.PENDING_FIRST_REVIEW

    rebuilt_content = SqlContentService(content.engine)
    rebuilt = SqlReviewService(content.engine, rebuilt_content)
    assert rebuilt.get_submission(submission.id) == submission
    assert rebuilt.list_submissions() == [submission]

    decision = rebuilt.decide(submission.id, "reviewer-1", ReviewDecision.APPROVE)
    rebuilt_again = SqlReviewService(content.engine, SqlContentService(content.engine))

    assert rebuilt_again.get_submission(submission.id).status is ReviewSubmissionStatus.APPROVED
    assert rebuilt_again.get_submission(submission.id).decision_id == decision.id
    assert rebuilt_again.get_decision(decision.id) == decision
    assert rebuilt_again.content.get_book(book.id).visibility is BookVisibility.PUBLIC
    assert rebuilt_again.content.get_chapter(version.chapter_id).published_version_id == version.id


def test_sql_review_validates_fixed_versions_before_persisting() -> None:
    review, content = _review()
    first_book, first_version = _fixed_version(content, "Book 1")
    _, other_version = _fixed_version(content, "Book 2")

    with pytest.raises(ValueError, match="does not belong"):
        review.submit_first_listing(first_book.id, [first_version.id, other_version.id])

    assert review.list_submissions() == []
    assert content.get_book(first_book.id).visibility is BookVisibility.PRIVATE


def test_sql_review_keeps_rejection_and_return_statuses() -> None:
    review, content = _review()
    rejected_book, rejected_version = _fixed_version(content, "Rejected")
    returned_book, returned_version = _fixed_version(content, "Returned")
    rejected = review.submit_first_listing(rejected_book.id, [rejected_version.id])
    returned = review.submit_first_listing(returned_book.id, [returned_version.id])

    review.decide(rejected.id, "reviewer-1", ReviewDecision.REJECT)
    review.decide(returned.id, "reviewer-1", ReviewDecision.RETURN_FOR_CHANGES)

    assert review.get_submission(rejected.id).status is ReviewSubmissionStatus.REJECTED
    assert review.get_submission(returned.id).status is ReviewSubmissionStatus.RETURNED
    assert content.get_book(rejected_book.id).visibility is BookVisibility.PENDING_FIRST_REVIEW
    assert content.get_book(returned_book.id).visibility is BookVisibility.PENDING_FIRST_REVIEW


def test_sql_review_requires_human_first_listing_approval() -> None:
    review, content = _review()
    book, version = _fixed_version(content)
    submission = review.submit_first_listing(book.id, [version.id])

    with pytest.raises(ValueError, match="human"):
        review.decide(submission.id, "machine-1", ReviewDecision.APPROVE, actor_type="machine")


def test_sql_review_collection_filters_by_assigned_staff_scope() -> None:
    review, content = _review()
    assigned_book, assigned_version = _fixed_version(content, "Assigned")
    other_book, other_version = _fixed_version(content, "Other")
    assigned = review.submit_first_listing(assigned_book.id, [assigned_version.id])
    other = review.submit_first_listing(other_book.id, [other_version.id])

    review.assign_submission(assigned.id, "staff-a")
    review.assign_submission(other.id, "staff-b")

    visible = review.list_submissions_for_scope("ASSIGNED", "staff-a")

    assert [item.id for item in visible] == [assigned.id]

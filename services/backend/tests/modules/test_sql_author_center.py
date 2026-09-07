import sqlalchemy as sa

from novel_platform.modules.author_center.sql_service import SqlAuthorCenterService


def _engine() -> sa.Engine:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table(
        "author_daily_writing_stats",
        metadata,
        sa.Column("author_id", sa.String(64), primary_key=True),
        sa.Column("business_date", sa.Date, primary_key=True),
        sa.Column("words", sa.BigInteger, nullable=False),
        sa.Column("goal", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "author_task_definitions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("target", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "author_task_progress",
        metadata,
        sa.Column("author_id", sa.String(64), primary_key=True),
        sa.Column("task_id", sa.String(64), primary_key=True),
        sa.Column("progress", sa.BigInteger, nullable=False),
        sa.Column("claimed", sa.Boolean, nullable=False),
        sa.Column("idempotency_key", sa.String(128), unique=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "writer_learning_contents",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "writer_learning_progress",
        metadata,
        sa.Column("author_id", sa.String(64), primary_key=True),
        sa.Column("content_id", sa.String(64), primary_key=True),
        sa.Column("percent", sa.SmallInteger, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "chapter_funnel_metrics",
        metadata,
        sa.Column("chapter_id", sa.String(64), primary_key=True),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("entrants", sa.BigInteger, nullable=False),
        sa.Column("completion_bps", sa.Integer, nullable=False),
        sa.Column("next_chapter_bps", sa.Integer, nullable=False),
        sa.Column("subscription_bps", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "author_appeals",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("subject_type", sa.String(32), nullable=False),
        sa.Column("subject_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    metadata.create_all(engine)
    return engine


def test_sql_author_center_persists_writer_facts_and_task_idempotency() -> None:
    engine = _engine()
    service = SqlAuthorCenterService(engine)
    service.record_daily_writing("author-1", "2026-09-05", 1200, 1000)
    service.record_daily_writing("author-1", "2026-09-04", 800, 1000)
    assert [item.business_date for item in service.calendar("author-1")] == [
        "2026-09-04",
        "2026-09-05",
    ]

    task = service.create_task("FIRST_CHAPTER", "完成首章", 1)
    first = service.progress_task("author-1", task.id, 1, "request-1")
    rebuilt = SqlAuthorCenterService(engine)
    assert rebuilt.progress_task("author-1", task.id, 1, "request-1") == first
    assert rebuilt.progress_task("author-1", task.id, 0, "request-2").claimed is False


def test_sql_author_center_persists_learning_funnel_and_appeal() -> None:
    service = SqlAuthorCenterService(_engine())
    lesson = service.publish_learning("开篇", "第一章")
    assert service.read_learning(lesson.id).title == "第一章"
    assert service.mark_learning_progress("author-1", lesson.id, 80) == 80
    assert service.learning_progress("author-1", lesson.id) == 80
    funnel = service.record_chapter_funnel("book-1", "chapter-1", 100, 7000, 4200, 1800)
    assert funnel.subscription_bps == 1800
    assert service.open_appeal("author-1", "CHAPTER", "chapter-1", "复核").status == "OPEN"

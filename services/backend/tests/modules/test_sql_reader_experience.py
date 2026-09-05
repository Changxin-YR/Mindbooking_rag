import sqlalchemy as sa
from sqlalchemy import create_engine

from novel_platform.modules.reader_experience.domain import CorrectionKind
from novel_platform.modules.reader_experience.sql_service import SqlReaderExperienceService


def _engine() -> sa.Engine:
    metadata = sa.MetaData()
    sa.Table(
        "book_user_ratings",
        metadata,
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
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "book_user_rating_versions",
        metadata,
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("rating_id", sa.String(64), nullable=False),
        sa.Column("overall_score", sa.SmallInteger, nullable=False),
        sa.Column("plot_score", sa.SmallInteger, nullable=False),
        sa.Column("character_score", sa.SmallInteger, nullable=False),
        sa.Column("writing_score", sa.SmallInteger, nullable=False),
        sa.Column("update_score", sa.SmallInteger, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "follow_relations",
        metadata,
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "user_growth_profiles",
        metadata,
        sa.Column("account_id", sa.String(64), primary_key=True),
        sa.Column("points", sa.BigInteger, nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("membership_level", sa.Integer, nullable=False),
        sa.Column("fan_level", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "user_growth_events",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("points", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "content_correction_reports",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("chapter_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("position", sa.BigInteger, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "minor_protection_profiles",
        metadata,
        sa.Column("account_id", sa.String(64), primary_key=True),
        sa.Column("is_minor", sa.Boolean, nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    return engine


def test_sql_reader_experience_reloads_rating_follow_growth_and_minor_facts() -> None:
    service = SqlReaderExperienceService(_engine())
    rating = service.rate("acct-1", "book-1", 5, 4, 5, 4, 1_000)
    service.rate("acct-1", "book-1", 4, 4, 4, 4, 1_200)
    assert service.follow("acct-1", "AUTHOR", "author-1")
    service.add_growth("acct-1", "READING", 100)
    service.submit_correction("acct-1", "book-1", "chapter-1", CorrectionKind.TYPO, 5, "错字")
    service.set_minor_protection("acct-1", True, "minor-v1")

    rebuilt = SqlReaderExperienceService(service.engine)

    history = rebuilt.rating_history("acct-1", "book-1")
    assert len(history) == 2
    assert history[0].id == rating.id == history[1].id
    assert rebuilt.following("acct-1") == (("AUTHOR", "author-1"),)
    assert rebuilt.growth("acct-1").points == 100
    assert rebuilt.minor_protection("acct-1").purchase_allowed is False

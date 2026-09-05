import sqlalchemy as sa
from sqlalchemy import create_engine

from novel_platform.modules.operation.domain import RankingKind, RetentionAction, RetentionPolicy
from novel_platform.modules.operation.sql_service import SqlOperationService


def _engine() -> sa.Engine:
    metadata = sa.MetaData()
    for name, columns in {
        "ranking_items": [
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("book_id", sa.String(64), nullable=False),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("score", sa.BigInteger, nullable=False),
            sa.Column("rank", sa.Integer, nullable=False),
            sa.Column("snapshot_id", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime, nullable=False),
        ],
        "recommendations": [
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("account_id", sa.String(64), nullable=False),
            sa.Column("book_id", sa.String(64), nullable=False),
            sa.Column("score", sa.BigInteger, nullable=False),
            sa.Column("personalized", sa.Boolean, nullable=False),
            sa.Column("created_at", sa.DateTime, nullable=False),
        ],
        "operation_jobs": [
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("job_type", sa.String(64), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("created_at", sa.DateTime, nullable=False),
        ],
        "export_jobs": [
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("requester_id", sa.String(64), nullable=False),
            sa.Column("resource_type", sa.String(64), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("created_at", sa.DateTime, nullable=False),
        ],
        "retention_policies": [
            sa.Column("resource_type", sa.String(64), primary_key=True),
            sa.Column("action", sa.String(32), nullable=False),
            sa.Column("days", sa.Integer, nullable=False),
            sa.Column("created_at", sa.DateTime, nullable=False),
        ],
        "operation_legal_holds": [
            sa.Column("resource_id", sa.String(64), primary_key=True),
            sa.Column("created_at", sa.DateTime, nullable=False),
        ],
        "operation_campaigns": [
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("title", sa.String(256), nullable=False),
            sa.Column("start_date", sa.String(32), nullable=False),
            sa.Column("end_date", sa.String(32), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("created_at", sa.DateTime, nullable=False),
        ],
        "operation_campaign_enrollments": [
            sa.Column("account_id", sa.String(64), primary_key=True),
            sa.Column("campaign_id", sa.String(64), primary_key=True),
            sa.Column("created_at", sa.DateTime, nullable=False),
        ],
        "operation_reward_grants": [
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("subject_id", sa.String(64), nullable=False),
            sa.Column("reward_type", sa.String(64), nullable=False),
            sa.Column("amount", sa.BigInteger, nullable=False),
            sa.Column("idempotency_key", sa.String(128), unique=True, nullable=False),
            sa.Column("created_at", sa.DateTime, nullable=False),
        ],
    }.items():
        sa.Table(name, metadata, *columns)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    return engine


def test_sql_operation_reloads_facts_and_keeps_reward_idempotency() -> None:
    engine = _engine()
    service = SqlOperationService(engine)
    items = service.publish_ranking(["b1", "b2"], RankingKind.ALGORITHM, [1, 9], "snap-1")
    service.set_retention_policy(RetentionPolicy("book", RetentionAction.DELETE, 30))
    service.mark_legal_hold("book-1")
    campaign = service.create_campaign("秋日征文", "2026-09-01", "2026-10-01")
    reward = service.grant_reward("author-1", "POINT", 10, "reward-1")

    rebuilt = SqlOperationService(engine)

    assert [item.book_id for item in rebuilt.public_rankings()] == ["b2", "b1"]
    assert rebuilt.retention_action("book-1", "book") is RetentionAction.KEEP
    assert rebuilt.enroll_campaign("account-1", campaign.id)
    assert not rebuilt.enroll_campaign("account-1", campaign.id)
    assert rebuilt.grant_reward("other", "POINT", 999, "reward-1") == reward
    assert len(items) == 2

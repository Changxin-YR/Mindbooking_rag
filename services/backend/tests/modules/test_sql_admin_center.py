import sqlalchemy as sa
from sqlalchemy import create_engine

from novel_platform.modules.admin_center.sql_service import SqlAdminCenterService


def _engine() -> sa.Engine:
    metadata = sa.MetaData()
    sa.Table(
        "review_rules",
        metadata,
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column("version", sa.String(64), primary_key=True),
        sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("recommended_action", sa.String(64), nullable=False),
        sa.Column("auto_block_policy", sa.Boolean, nullable=False),
        sa.Column("subject_types_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "reviewer_quality_metrics",
        metadata,
        sa.Column("reviewer_id", sa.String(64), primary_key=True),
        sa.Column("accuracy_bps", sa.Integer, nullable=False),
        sa.Column("false_positive_bps", sa.Integer, nullable=False),
        sa.Column("miss_bps", sa.Integer, nullable=False),
        sa.Column("overturn_bps", sa.Integer, nullable=False),
        sa.Column("avg_handle_seconds", sa.Integer, nullable=False),
        sa.Column("complaint_bps", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "author_alerts",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("risk_level", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "support_csat_records",
        metadata,
        sa.Column("ticket_id", sa.String(64), primary_key=True),
        sa.Column("score", sa.SmallInteger, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    return engine


def test_sql_admin_center_reloads_rules_alerts_and_csat_dashboard() -> None:
    engine = _engine()
    service = SqlAdminCenterService(engine)
    rule = service.add_review_rule("SPAM", "HIGH", "BLOCK", True, ("BOOK",), "v1")
    service.record_reviewer_quality("reviewer-1", 9_000, 100, 100, 50, 60, 20)
    service.create_author_alert("author-1", "RISK", "人工复核", "HIGH")
    service.record_csat("ticket-1", 5)

    rebuilt = SqlAdminCenterService(engine)

    assert rebuilt.list_review_rules() == (rule,)
    assert rebuilt.support_dashboard() == {"csat_count": 1, "open_alert_count": 1}

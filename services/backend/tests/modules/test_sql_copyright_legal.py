import sqlalchemy as sa
from sqlalchemy import create_engine

from novel_platform.modules.copyright.sql_service import SqlCopyrightService
from novel_platform.modules.legal.sql_service import SqlLegalService


def _engine() -> sa.Engine:
    metadata = sa.MetaData()
    sa.Table(
        "copyright_dossiers",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "copyright_right_items",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("dossier_id", sa.String(64), nullable=False),
        sa.Column("region", sa.String(64), nullable=False),
        sa.Column("language", sa.String(32), nullable=False),
        sa.Column("media", sa.String(32), nullable=False),
        sa.Column("exclusive", sa.Boolean, nullable=False),
        sa.Column("start_year", sa.Integer, nullable=False),
        sa.Column("end_year", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "copyright_complaints",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("claimant_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("counter_notice", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "copyright_complaint_evidence",
        metadata,
        sa.Column("complaint_id", sa.String(64), primary_key=True),
        sa.Column("evidence_id", sa.String(64), primary_key=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "legal_cases",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "legal_holds",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    return engine


def test_sql_copyright_and_legal_reload_historical_facts() -> None:
    engine = _engine()
    copyright_service = SqlCopyrightService(engine)
    dossier = copyright_service.create_dossier("book-1")
    right = copyright_service.add_right(dossier.id, "CN", "zh", "TEXT", True, 2026, 2028)
    complaint = copyright_service.complain("book-1", "claimant-1", "侵权")
    copyright_service.attach_evidence(complaint.id, "evidence-1")
    copyright_service.counter_notice(complaint.id, "反通知")

    legal_service = SqlLegalService(engine)
    case = legal_service.open_case("book-1")
    hold = legal_service.hold(case.id, "book-1")

    rebuilt_copyright = SqlCopyrightService(engine)
    rebuilt_legal = SqlLegalService(engine)

    assert rebuilt_copyright.dossiers[dossier.id].right_ids == [right.id]
    assert rebuilt_copyright.complaints[complaint.id].evidence_ids == ["evidence-1"]
    assert rebuilt_copyright.complaints[complaint.id].status == "COUNTER_NOTICE"
    assert rebuilt_legal.is_held("book-1")
    assert rebuilt_legal.holds[hold.id].status == "ACTIVE"

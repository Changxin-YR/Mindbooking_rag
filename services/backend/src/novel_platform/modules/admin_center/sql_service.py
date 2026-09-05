"""SQLAlchemy adapter for Admin Center operational facts."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from novel_platform.modules.admin_center.application import AdminCenterService
from novel_platform.modules.admin_center.domain import (
    AuthorAlert,
    CsatRecord,
    ReviewerQuality,
    ReviewRule,
)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class SqlAdminCenterService(AdminCenterService):
    """Persist Admin Center facts and retain User360 as a computed view."""

    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.engine = engine
        metadata = sa.MetaData()
        self._rules: Any = sa.Table("review_rules", metadata, autoload_with=engine)
        self._quality: Any = sa.Table("reviewer_quality_metrics", metadata, autoload_with=engine)
        self._alerts: Any = sa.Table("author_alerts", metadata, autoload_with=engine)
        self._csat: Any = sa.Table("support_csat_records", metadata, autoload_with=engine)

    def add_review_rule(
        self,
        code: str,
        severity: str,
        recommended_action: str,
        auto_block_policy: bool,
        subject_types: tuple[str, ...],
        version: str,
    ) -> ReviewRule:
        if (
            not code.strip()
            or not severity.strip()
            or not recommended_action.strip()
            or not version.strip()
            or not subject_types
        ):
            raise ValueError("REVIEW_RULE_INVALID")
        rule = ReviewRule(
            code, severity, recommended_action, auto_block_policy, subject_types, version
        )
        with self.engine.begin() as connection:
            values = {
                "severity": severity,
                "recommended_action": recommended_action,
                "auto_block_policy": auto_block_policy,
                "subject_types_json": json.dumps(subject_types, ensure_ascii=False),
            }
            exists = connection.execute(
                sa.select(self._rules.c.code).where(
                    self._rules.c.code == code, self._rules.c.version == version
                )
            ).scalar_one_or_none()
            if exists is None:
                connection.execute(
                    self._rules.insert().values(
                        code=code,
                        version=version,
                        created_at=datetime.now(UTC),
                        **values,
                    )
                )
            else:
                connection.execute(
                    self._rules.update()
                    .where(self._rules.c.code == code, self._rules.c.version == version)
                    .values(**values)
                )
        return rule

    def list_review_rules(self) -> tuple[ReviewRule, ...]:
        with self.engine.begin() as connection:
            rows = connection.execute(
                sa.select(self._rules).order_by(self._rules.c.created_at, self._rules.c.code)
            ).mappings()
            return tuple(self._rule_from_row(row) for row in rows)

    def record_reviewer_quality(
        self,
        reviewer_id: str,
        accuracy_bps: int,
        false_positive_bps: int,
        miss_bps: int,
        overturn_bps: int,
        avg_handle_seconds: int,
        complaint_bps: int,
    ) -> ReviewerQuality:
        rates = (accuracy_bps, false_positive_bps, miss_bps, overturn_bps, complaint_bps)
        if any(rate < 0 or rate > 10_000 for rate in rates) or avg_handle_seconds < 0:
            raise ValueError("REVIEWER_QUALITY_INVALID")
        quality = ReviewerQuality(
            reviewer_id,
            accuracy_bps,
            false_positive_bps,
            miss_bps,
            overturn_bps,
            avg_handle_seconds,
            complaint_bps,
        )
        with self.engine.begin() as connection:
            values = {
                "accuracy_bps": accuracy_bps,
                "false_positive_bps": false_positive_bps,
                "miss_bps": miss_bps,
                "overturn_bps": overturn_bps,
                "avg_handle_seconds": avg_handle_seconds,
                "complaint_bps": complaint_bps,
            }
            exists = connection.execute(
                sa.select(self._quality.c.reviewer_id).where(
                    self._quality.c.reviewer_id == reviewer_id
                )
            ).scalar_one_or_none()
            if exists is None:
                connection.execute(
                    self._quality.insert().values(
                        reviewer_id=reviewer_id, created_at=datetime.now(UTC), **values
                    )
                )
            else:
                connection.execute(
                    self._quality.update()
                    .where(self._quality.c.reviewer_id == reviewer_id)
                    .values(**values)
                )
        return quality

    def create_author_alert(
        self, author_id: str, alert_type: str, summary: str, risk_level: str
    ) -> AuthorAlert:
        if not author_id.strip() or not alert_type.strip() or not summary.strip():
            raise ValueError("AUTHOR_ALERT_INVALID")
        alert = AuthorAlert(_id("ALERT"), author_id, alert_type, summary.strip(), risk_level)
        with self.engine.begin() as connection:
            connection.execute(
                self._alerts.insert().values(
                    id=alert.id,
                    author_id=alert.author_id,
                    alert_type=alert.alert_type,
                    summary=alert.summary,
                    risk_level=alert.risk_level,
                    status=alert.status,
                    created_at=datetime.now(UTC),
                )
            )
        return alert

    def record_csat(self, ticket_id: str, score: int) -> CsatRecord:
        if not 1 <= score <= 5:
            raise ValueError("CSAT_SCORE_INVALID")
        record = CsatRecord(ticket_id, score)
        with self.engine.begin() as connection:
            exists = connection.execute(
                sa.select(self._csat.c.ticket_id).where(self._csat.c.ticket_id == ticket_id)
            ).scalar_one_or_none()
            if exists is None:
                connection.execute(
                    self._csat.insert().values(
                        ticket_id=ticket_id, score=score, created_at=datetime.now(UTC)
                    )
                )
            else:
                connection.execute(
                    self._csat.update()
                    .where(self._csat.c.ticket_id == ticket_id)
                    .values(score=score)
                )
        return record

    def support_dashboard(self) -> dict[str, int]:
        with self.engine.begin() as connection:
            csat_count = connection.execute(
                sa.select(sa.func.count()).select_from(self._csat)
            ).scalar_one()
            open_alert_count = connection.execute(
                sa.select(sa.func.count())
                .select_from(self._alerts)
                .where(self._alerts.c.status == "OPEN")
            ).scalar_one()
            return {"csat_count": int(csat_count), "open_alert_count": int(open_alert_count)}

    @staticmethod
    def _rule_from_row(row: sa.RowMapping) -> ReviewRule:
        return ReviewRule(
            str(row["code"]),
            str(row["severity"]),
            str(row["recommended_action"]),
            bool(row["auto_block_policy"]),
            tuple(json.loads(str(row["subject_types_json"]))),
            str(row["version"]),
        )


__all__ = ["SqlAdminCenterService"]

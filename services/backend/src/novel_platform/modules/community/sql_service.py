"""SQLAlchemy adapter for community report facts."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from novel_platform.modules.community.application import CommunityService
from novel_platform.modules.community.domain import ReportCase, ReportStatus, ReportSubmission


class SqlCommunityService(CommunityService):
    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.engine = engine
        metadata = sa.MetaData()
        self._cases: Any = sa.Table("community_report_cases", metadata, autoload_with=engine)
        self._submissions: Any = sa.Table(
            "community_report_submissions", metadata, autoload_with=engine
        )

    def submit_report(
        self, content_type: str, content_id: str, reporter_id: str, reason: str
    ) -> ReportCase:
        if not content_type or not content_id or not reporter_id or not reason:
            raise ValueError("report fields are required")
        with self.engine.begin() as connection:
            case = self._case_row(connection, content_type, content_id, lock=True)
            if case is None:
                case_id = f"CASE_{uuid4().hex}"
                try:
                    with connection.begin_nested():
                        connection.execute(
                            self._cases.insert().values(
                                id=case_id,
                                content_type=content_type,
                                content_id=content_id,
                                status=ReportStatus.OPEN.value,
                                created_at=datetime.now(UTC),
                            )
                        )
                except IntegrityError:
                    case = self._case_row(connection, content_type, content_id, lock=True)
                    if case is None:
                        raise
            else:
                case_id = str(case["id"])
            if case is None:
                case = self._case_row(connection, content_type, content_id, lock=True)
            if case is None:
                raise RuntimeError("report case was not created")
            case_id = str(case["id"])
            duplicate = connection.execute(
                sa.select(self._submissions.c.id).where(
                    self._submissions.c.case_id == case_id,
                    self._submissions.c.reporter_id == reporter_id,
                )
            ).scalar_one_or_none()
            if duplicate is not None:
                raise ValueError("reporter already submitted for content")
            try:
                with connection.begin_nested():
                    connection.execute(
                        self._submissions.insert().values(
                            id=f"RPT_{uuid4().hex}",
                            case_id=case_id,
                            reporter_id=reporter_id,
                            reason=reason,
                            created_at=datetime.now(UTC),
                        )
                    )
            except IntegrityError as exc:
                raise ValueError("reporter already submitted for content") from exc
            return self._case_from_connection(connection, case_id)

    def get_case(self, case_id: str) -> ReportCase:
        with self.engine.begin() as connection:
            row = (
                connection.execute(sa.select(self._cases).where(self._cases.c.id == case_id))
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError(f"report case {case_id} not found")
            return self._case_from_connection(connection, case_id, row)

    def _case_row(
        self, connection: Connection, content_type: str, content_id: str, *, lock: bool = False
    ) -> sa.RowMapping | None:
        query = sa.select(self._cases).where(
            self._cases.c.content_type == content_type,
            self._cases.c.content_id == content_id,
        )
        if lock:
            query = query.with_for_update()
        return connection.execute(query).mappings().one_or_none()

    def _case_from_connection(
        self, connection: Connection, case_id: str, row: sa.RowMapping | None = None
    ) -> ReportCase:
        row = (
            row
            or connection.execute(sa.select(self._cases).where(self._cases.c.id == case_id))
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise KeyError(f"report case {case_id} not found")
        submissions = connection.execute(
            sa.select(self._submissions)
            .where(self._submissions.c.case_id == case_id)
            .order_by(self._submissions.c.created_at, self._submissions.c.id)
        ).mappings()
        return ReportCase(
            id=str(row["id"]),
            content_type=str(row["content_type"]),
            content_id=str(row["content_id"]),
            status=ReportStatus(str(row["status"])),
            submissions=[
                ReportSubmission(
                    id=str(item["id"]),
                    case_id=str(item["case_id"]),
                    reporter_id=str(item["reporter_id"]),
                    reason=str(item["reason"]),
                )
                for item in submissions
            ],
        )

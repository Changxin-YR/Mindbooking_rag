"""SQLAlchemy adapter for copyright dossiers, rights, and complaints."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from novel_platform.modules.copyright.application import CopyrightService
from novel_platform.modules.copyright.domain import CopyrightComplaint, CopyrightDossier, RightItem


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class SqlCopyrightService(CopyrightService):
    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.engine = engine
        metadata = sa.MetaData()
        self._dossier_table: Any = sa.Table("copyright_dossiers", metadata, autoload_with=engine)
        self._right_table: Any = sa.Table("copyright_right_items", metadata, autoload_with=engine)
        self._complaint_table: Any = sa.Table(
            "copyright_complaints", metadata, autoload_with=engine
        )
        self._evidence_table: Any = sa.Table(
            "copyright_complaint_evidence", metadata, autoload_with=engine
        )
        self._reload()

    def _reload(self) -> None:
        with self.engine.begin() as connection:
            dossiers = connection.execute(sa.select(self._dossier_table)).mappings()
            self.dossiers = {
                str(row["id"]): CopyrightDossier(str(row["id"]), str(row["book_id"]))
                for row in dossiers
            }
            rights = connection.execute(sa.select(self._right_table)).mappings()
            self.rights = {
                str(row["id"]): RightItem(
                    str(row["id"]),
                    str(row["dossier_id"]),
                    str(row["region"]),
                    str(row["language"]),
                    str(row["media"]),
                    bool(row["exclusive"]),
                    int(row["start_year"]),
                    int(row["end_year"]),
                )
                for row in rights
            }
            for right in self.rights.values():
                if right.dossier_id in self.dossiers:
                    self.dossiers[right.dossier_id].right_ids.append(right.id)
            complaints = connection.execute(sa.select(self._complaint_table)).mappings()
            self.complaints = {
                str(row["id"]): CopyrightComplaint(
                    str(row["id"]),
                    str(row["book_id"]),
                    str(row["claimant_id"]),
                    str(row["reason"]),
                    status=str(row["status"]),
                    counter_notice=str(row["counter_notice"])
                    if row["counter_notice"] is not None
                    else None,
                )
                for row in complaints
            }
            evidence = connection.execute(sa.select(self._evidence_table)).mappings()
            for row in evidence:
                complaint = self.complaints.get(str(row["complaint_id"]))
                if complaint is not None:
                    complaint.evidence_ids.append(str(row["evidence_id"]))

    def create_dossier(self, book_id: str) -> CopyrightDossier:
        dossier = CopyrightDossier(_id("DOS"), book_id)
        with self.engine.begin() as connection:
            connection.execute(
                self._dossier_table.insert().values(
                    id=dossier.id, book_id=dossier.book_id, created_at=datetime.now(UTC)
                )
            )
        self.dossiers[dossier.id] = dossier
        return dossier

    def add_right(
        self,
        dossier_id: str,
        region: str,
        language: str,
        media: str,
        exclusive: bool,
        start_year: int,
        end_year: int,
    ) -> RightItem:
        if end_year <= start_year:
            raise ValueError("INVALID_RIGHT_RANGE")
        with self.engine.begin() as connection:
            exists = connection.execute(
                sa.select(self._dossier_table.c.id).where(self._dossier_table.c.id == dossier_id)
            ).scalar_one_or_none()
            if exists is None:
                raise KeyError(dossier_id)
            conflict = connection.execute(
                sa.select(self._right_table.c.id).where(
                    self._right_table.c.region == region,
                    self._right_table.c.language == language,
                    self._right_table.c.media == media,
                    self._right_table.c.exclusive.is_(True),
                    sa.true() if exclusive else sa.false(),
                    self._right_table.c.start_year < end_year,
                    start_year < self._right_table.c.end_year,
                )
            ).scalar_one_or_none()
            if conflict is not None:
                raise ValueError("RIGHT_CONFLICT_MANUAL_LEGAL_REVIEW")
            item = RightItem(
                _id("RIGHT"), dossier_id, region, language, media, exclusive, start_year, end_year
            )
            connection.execute(
                self._right_table.insert().values(
                    id=item.id,
                    dossier_id=item.dossier_id,
                    region=item.region,
                    language=item.language,
                    media=item.media,
                    exclusive=item.exclusive,
                    start_year=item.start_year,
                    end_year=item.end_year,
                    created_at=datetime.now(UTC),
                )
            )
        self.rights[item.id] = item
        self.dossiers[dossier_id].right_ids.append(item.id)
        return item

    def complain(self, book_id: str, claimant_id: str, reason: str) -> CopyrightComplaint:
        complaint = CopyrightComplaint(_id("CMP"), book_id, claimant_id, reason)
        with self.engine.begin() as connection:
            connection.execute(
                self._complaint_table.insert().values(
                    id=complaint.id,
                    book_id=complaint.book_id,
                    claimant_id=complaint.claimant_id,
                    reason=complaint.reason,
                    status=complaint.status,
                    counter_notice=complaint.counter_notice,
                    created_at=datetime.now(UTC),
                )
            )
        self.complaints[complaint.id] = complaint
        return complaint

    def attach_evidence(self, complaint_id: str, evidence_id: str) -> CopyrightComplaint:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._complaint_table).where(
                        self._complaint_table.c.id == complaint_id
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError(complaint_id)
            exists = connection.execute(
                sa.select(self._evidence_table.c.evidence_id).where(
                    self._evidence_table.c.complaint_id == complaint_id,
                    self._evidence_table.c.evidence_id == evidence_id,
                )
            ).scalar_one_or_none()
            if exists is None:
                connection.execute(
                    self._evidence_table.insert().values(
                        complaint_id=complaint_id,
                        evidence_id=evidence_id,
                        created_at=datetime.now(UTC),
                    )
                )
            connection.execute(
                self._complaint_table.update()
                .where(self._complaint_table.c.id == complaint_id)
                .values(status="EVIDENCE_REVIEW")
            )
        complaint = self.complaints[complaint_id]
        if evidence_id not in complaint.evidence_ids:
            complaint.evidence_ids.append(evidence_id)
        complaint.status = "EVIDENCE_REVIEW"
        return complaint

    def counter_notice(self, complaint_id: str, notice: str) -> CopyrightComplaint:
        with self.engine.begin() as connection:
            result = connection.execute(
                self._complaint_table.update()
                .where(self._complaint_table.c.id == complaint_id)
                .values(counter_notice=notice, status="COUNTER_NOTICE")
            )
            if result.rowcount == 0:
                raise KeyError(complaint_id)
        complaint = self.complaints[complaint_id]
        complaint.counter_notice = notice
        complaint.status = "COUNTER_NOTICE"
        return complaint


__all__ = ["SqlCopyrightService"]

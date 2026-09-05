"""SQLAlchemy adapter for legal cases and legal holds."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from novel_platform.modules.legal.application import LegalService
from novel_platform.modules.legal.domain import LegalCase, LegalHold


class SqlLegalService(LegalService):
    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.engine = engine
        metadata = sa.MetaData()
        self._cases: Any = sa.Table("legal_cases", metadata, autoload_with=engine)
        self._holds: Any = sa.Table("legal_holds", metadata, autoload_with=engine)
        self._reload()

    def _reload(self) -> None:
        with self.engine.begin() as connection:
            self.cases = {
                str(row["id"]): LegalCase(str(row["id"]), str(row["subject"]), str(row["status"]))
                for row in connection.execute(sa.select(self._cases)).mappings()
            }
            self.holds = {
                str(row["id"]): LegalHold(
                    str(row["id"]), str(row["case_id"]), str(row["resource_id"]), str(row["status"])
                )
                for row in connection.execute(sa.select(self._holds)).mappings()
            }

    def open_case(self, subject: str) -> LegalCase:
        case = LegalCase(f"LGL_{uuid4().hex}", subject)
        with self.engine.begin() as connection:
            connection.execute(
                self._cases.insert().values(
                    id=case.id,
                    subject=case.subject,
                    status=case.status,
                    created_at=datetime.now(UTC),
                )
            )
        self.cases[case.id] = case
        return case

    def hold(self, case_id: str, resource_id: str) -> LegalHold:
        with self.engine.begin() as connection:
            exists = connection.execute(
                sa.select(self._cases.c.id).where(self._cases.c.id == case_id)
            ).scalar_one_or_none()
            if exists is None:
                raise KeyError(case_id)
            item = LegalHold(f"HLD_{uuid4().hex}", case_id, resource_id)
            connection.execute(
                self._holds.insert().values(
                    id=item.id,
                    case_id=item.case_id,
                    resource_id=item.resource_id,
                    status=item.status,
                    created_at=datetime.now(UTC),
                )
            )
        self.holds[item.id] = item
        return item

    def release(self, hold_id: str) -> LegalHold:
        with self.engine.begin() as connection:
            result = connection.execute(
                self._holds.update().where(self._holds.c.id == hold_id).values(status="RELEASED")
            )
            if result.rowcount == 0:
                raise KeyError(hold_id)
        item = self.holds[hold_id]
        item.status = "RELEASED"
        return item

    def is_held(self, resource_id: str) -> bool:
        with self.engine.begin() as connection:
            return (
                connection.execute(
                    sa.select(self._holds.c.id).where(
                        self._holds.c.resource_id == resource_id,
                        self._holds.c.status == "ACTIVE",
                    )
                ).scalar_one_or_none()
                is not None
            )


__all__ = ["SqlLegalService"]

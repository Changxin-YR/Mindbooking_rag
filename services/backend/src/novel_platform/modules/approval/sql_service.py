"""SQLAlchemy adapter for maker-checker approval facts."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from novel_platform.modules.approval.application import ApprovalService, MakerCheckerError
from novel_platform.modules.approval.domain import ApprovalRequest, ApprovalStatus


class SqlApprovalService(ApprovalService):
    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.engine = engine
        metadata = sa.MetaData()
        self._requests: Any = sa.Table("approval_requests", metadata, autoload_with=engine)
        self._decisions: Any = sa.Table("approval_decisions", metadata, autoload_with=engine)

    def request(self, action: str, requester_id: str, critical: bool) -> ApprovalRequest:
        if not action or not requester_id:
            raise ValueError("approval fields are required")
        approval = ApprovalRequest(
            id=f"APR_{uuid4().hex}",
            action=action,
            requester_id=requester_id,
            critical=critical,
        )
        with self.engine.begin() as connection:
            connection.execute(
                self._requests.insert().values(
                    id=approval.id,
                    action=approval.action,
                    requester_id=approval.requester_id,
                    critical=approval.critical,
                    status=approval.status.value,
                    created_at=datetime.now(UTC),
                )
            )
        return approval

    def get(self, approval_id: str) -> ApprovalRequest:
        with self.engine.begin() as connection:
            return self._get_from_connection(connection, approval_id)

    def approve(self, approval_id: str, approver_id: str) -> ApprovalRequest:
        return self._decide(approval_id, approver_id, ApprovalStatus.APPROVED)

    def reject(self, approval_id: str, approver_id: str) -> ApprovalRequest:
        return self._decide(approval_id, approver_id, ApprovalStatus.REJECTED)

    def _decide(
        self, approval_id: str, approver_id: str, status: ApprovalStatus
    ) -> ApprovalRequest:
        with self.engine.begin() as connection:
            approval = self._get_from_connection(connection, approval_id, lock=True)
            if approval.status is not ApprovalStatus.PENDING:
                raise ValueError("approval request is already decided")
            if approval.critical and approval.requester_id == approver_id:
                action = "approve" if status is ApprovalStatus.APPROVED else "reject"
                raise MakerCheckerError(f"requester cannot {action} critical action")
            connection.execute(
                self._decisions.insert().values(
                    id=f"APD_{uuid4().hex}",
                    request_id=approval.id,
                    approver_id=approver_id,
                    decision="APPROVE" if status is ApprovalStatus.APPROVED else "REJECT",
                    created_at=datetime.now(UTC),
                )
            )
            connection.execute(
                self._requests.update()
                .where(self._requests.c.id == approval.id)
                .values(status=status.value)
            )
            approval.status = status
            return approval

    def _get_from_connection(
        self, connection: Connection, approval_id: str, *, lock: bool = False
    ) -> ApprovalRequest:
        query = sa.select(self._requests).where(self._requests.c.id == approval_id)
        if lock:
            query = query.with_for_update()
        row = connection.execute(query).mappings().one_or_none()
        if row is None:
            raise KeyError(approval_id)
        return ApprovalRequest(
            id=str(row["id"]),
            action=str(row["action"]),
            requester_id=str(row["requester_id"]),
            critical=bool(row["critical"]),
            status=ApprovalStatus(str(row["status"])),
        )

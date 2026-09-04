from uuid import uuid4

from novel_platform.modules.approval.domain import ApprovalRequest, ApprovalStatus


class MakerCheckerError(ValueError):
    pass


class ApprovalService:
    def __init__(self) -> None:
        self._requests: dict[str, ApprovalRequest] = {}

    def request(self, action: str, requester_id: str, critical: bool) -> ApprovalRequest:
        if not action or not requester_id:
            raise ValueError("approval fields are required")
        approval = ApprovalRequest(
            id=f"APR_{uuid4().hex}", action=action, requester_id=requester_id, critical=critical
        )
        self._requests[approval.id] = approval
        return approval

    def get(self, approval_id: str) -> ApprovalRequest:
        return self._requests[approval_id]

    def approve(self, approval_id: str, approver_id: str) -> ApprovalRequest:
        approval = self.get(approval_id)
        if approval.status is not ApprovalStatus.PENDING:
            raise ValueError("approval request is already decided")
        if approval.critical and approval.requester_id == approver_id:
            raise MakerCheckerError("requester cannot approve critical action")
        approval.status = ApprovalStatus.APPROVED
        return approval

    def reject(self, approval_id: str, approver_id: str) -> ApprovalRequest:
        approval = self.get(approval_id)
        if approval.status is not ApprovalStatus.PENDING:
            raise ValueError("approval request is already decided")
        if approval.critical and approval.requester_id == approver_id:
            raise MakerCheckerError("requester cannot reject critical action")
        approval.status = ApprovalStatus.REJECTED
        return approval

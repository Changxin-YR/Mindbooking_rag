from dataclasses import dataclass

from novel_platform.modules.platform.domain import DataScope, Permission, StaffAccount, StaffStatus
from novel_platform.modules.platform.repository import PlatformRepository


class DuplicateStaffError(ValueError):
    pass


class StaffNotFoundError(LookupError):
    pass


class AccessDeniedError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class StaffResult:
    id: str
    employee_code: str
    department: str
    status: StaffStatus
    platform_account_id: str | None


class PlatformApplication:
    def __init__(self, repository: PlatformRepository) -> None:
        self.repository = repository

    def create_staff(self, employee_code: str, department: str) -> StaffResult:
        staff = StaffAccount.create(employee_code, department)
        if self.repository.has_employee_code(staff.employee_code):
            raise DuplicateStaffError("employee_code already exists")
        try:
            self.repository.create_staff(staff)
        except ValueError as exc:
            raise DuplicateStaffError("employee_code already exists") from exc
        return self._result(staff)

    def grant_permission(self, staff_id: str, permission: str) -> None:
        self._require_staff(staff_id)
        self.repository.grant_permission(Permission.create(staff_id, permission))

    def grant_data_scope(self, staff_id: str, scope_type: str, scope_value: str) -> None:
        self._require_staff(staff_id)
        self.repository.grant_data_scope(DataScope.create(staff_id, scope_type, scope_value))

    def can_access(self, staff_id: str, permission: str, scope_type: str, scope_value: str) -> bool:
        staff = self._require_staff(staff_id)
        if (
            staff.status is not StaffStatus.ACTIVE
            or permission not in self.repository.permissions_for(staff_id)
        ):
            return False
        scopes = self.repository.scopes_for(staff_id)
        return ("global", "*") in scopes or (scope_type, scope_value) in scopes

    def require_access(
        self, staff_id: str, permission: str, scope_type: str, scope_value: str
    ) -> None:
        if not self.can_access(staff_id, permission, scope_type, scope_value):
            raise AccessDeniedError("staff lacks permission or data scope")

    def _require_staff(self, staff_id: str) -> StaffAccount:
        staff = self.repository.staff(staff_id)
        if staff is None:
            raise StaffNotFoundError("staff account does not exist")
        return staff

    def _result(self, staff: StaffAccount) -> StaffResult:
        return StaffResult(
            staff.id, staff.employee_code, staff.department, staff.status, staff.platform_account_id
        )


__all__ = [
    "AccessDeniedError",
    "DuplicateStaffError",
    "PlatformApplication",
    "StaffNotFoundError",
    "StaffResult",
]

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

    def change_staff_status(self, staff_id: str, status: StaffStatus) -> StaffResult:
        staff = self._require_staff(staff_id)
        allowed = {
            StaffStatus.PENDING_ACTIVATION: {StaffStatus.ACTIVE, StaffStatus.DISABLED},
            StaffStatus.ACTIVE: {
                StaffStatus.LOCKED,
                StaffStatus.DISABLED,
                StaffStatus.OFFBOARDED,
            },
            StaffStatus.LOCKED: {StaffStatus.ACTIVE, StaffStatus.DISABLED, StaffStatus.OFFBOARDED},
            StaffStatus.DISABLED: {StaffStatus.ACTIVE, StaffStatus.OFFBOARDED},
            StaffStatus.OFFBOARDED: set(),
        }
        if status is staff.status:
            return self._result(staff)
        if status not in allowed[staff.status]:
            raise ValueError("STAFF_STATUS_TRANSITION_INVALID")
        return self._result(self.repository.update_staff_status(staff_id, status))

    def grant_data_scope(self, staff_id: str, scope_type: str, scope_value: str) -> None:
        self._require_staff(staff_id)
        self.repository.grant_data_scope(DataScope.create(staff_id, scope_type, scope_value))

    def staff_for_employee_code(self, employee_code: str) -> StaffAccount:
        staff = self.repository.staff_for_employee_code(employee_code.strip())
        if staff is None:
            raise StaffNotFoundError("staff account does not exist")
        return staff

    def can_access(self, staff_id: str, permission: str, scope_type: str, scope_value: str) -> bool:
        staff = self._require_staff(staff_id)
        if staff.status is not StaffStatus.ACTIVE or not _has_permission(
            self.repository.permissions_for(staff_id), permission
        ):
            return False
        requested_scope = (scope_type.upper(), scope_value.strip())
        scopes = {
            (stored_type.upper(), stored_value.strip())
            for stored_type, stored_value in self.repository.scopes_for(staff_id)
        }
        return any(
            (stored_type in {"ALL", "GLOBAL"} and stored_value == "*")
            or (stored_type, stored_value) == requested_scope
            for stored_type, stored_value in scopes
        )

    def has_permission(self, staff_id: str, permission: str) -> bool:
        staff = self._require_staff(staff_id)
        return staff.status is StaffStatus.ACTIVE and _has_permission(
            self.repository.permissions_for(staff_id), permission
        )

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


def _has_permission(granted: set[str], requested: str) -> bool:
    resource, _, action = requested.partition(".")
    return (
        requested in granted
        or "*.*" in granted
        or f"{resource}.*" in granted
        or (resource == "*" and action == "*")
    )

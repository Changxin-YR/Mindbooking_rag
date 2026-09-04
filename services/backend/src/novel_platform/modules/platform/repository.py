from threading import RLock
from typing import Protocol

from novel_platform.modules.platform.domain import DataScope, Permission, StaffAccount


class PlatformRepository(Protocol):
    def create_staff(self, staff: StaffAccount) -> None: ...

    def staff(self, staff_id: str) -> StaffAccount | None: ...

    def has_employee_code(self, employee_code: str) -> bool: ...

    def grant_permission(self, permission: Permission) -> None: ...

    def grant_data_scope(self, scope: DataScope) -> None: ...

    def permissions_for(self, staff_id: str) -> set[str]: ...

    def scopes_for(self, staff_id: str) -> set[tuple[str, str]]: ...


class InMemoryPlatformRepository:
    """Development repository; production wiring must provide a durable adapter."""

    def __init__(self) -> None:
        self._guard = RLock()
        self._staff: dict[str, StaffAccount] = {}
        self._employee_codes: set[str] = set()
        self._permissions: dict[str, set[str]] = {}
        self._scopes: dict[str, set[tuple[str, str]]] = {}

    def create_staff(self, staff: StaffAccount) -> None:
        with self._guard:
            if staff.employee_code in self._employee_codes:
                raise ValueError("employee_code already exists")
            self._staff[staff.id] = staff
            self._employee_codes.add(staff.employee_code)

    def staff(self, staff_id: str) -> StaffAccount | None:
        with self._guard:
            return self._staff.get(staff_id)

    def has_employee_code(self, employee_code: str) -> bool:
        with self._guard:
            return employee_code in self._employee_codes

    def grant_permission(self, permission: Permission) -> None:
        with self._guard:
            if permission.staff_id not in self._staff:
                raise KeyError(permission.staff_id)
            self._permissions.setdefault(permission.staff_id, set()).add(permission.name)

    def grant_data_scope(self, scope: DataScope) -> None:
        with self._guard:
            if scope.staff_id not in self._staff:
                raise KeyError(scope.staff_id)
            self._scopes.setdefault(scope.staff_id, set()).add(
                (scope.scope_type, scope.scope_value)
            )

    def permissions_for(self, staff_id: str) -> set[str]:
        with self._guard:
            return set(self._permissions.get(staff_id, set()))

    def scopes_for(self, staff_id: str) -> set[tuple[str, str]]:
        with self._guard:
            return set(self._scopes.get(staff_id, set()))

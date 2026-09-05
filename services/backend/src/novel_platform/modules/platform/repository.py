from threading import RLock
from typing import Protocol

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from novel_platform.modules.platform.domain import DataScope, Permission, StaffAccount, StaffStatus


class PlatformRepository(Protocol):
    def create_staff(self, staff: StaffAccount) -> None: ...

    def staff(self, staff_id: str) -> StaffAccount | None: ...

    def staff_for_employee_code(self, employee_code: str) -> StaffAccount | None: ...

    def update_staff_status(self, staff_id: str, status: StaffStatus) -> StaffAccount: ...

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

    def staff_for_employee_code(self, employee_code: str) -> StaffAccount | None:
        with self._guard:
            return next(
                (staff for staff in self._staff.values() if staff.employee_code == employee_code),
                None,
            )

    def has_employee_code(self, employee_code: str) -> bool:
        with self._guard:
            return employee_code in self._employee_codes

    def update_staff_status(self, staff_id: str, status: StaffStatus) -> StaffAccount:
        with self._guard:
            staff = self._staff[staff_id]
            updated = StaffAccount(
                staff.id, staff.employee_code, staff.department, status, staff.platform_account_id
            )
            self._staff[staff_id] = updated
            return updated

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


staff_accounts = sa.table(
    "staff_accounts",
    sa.column("id", sa.String),
    sa.column("employee_code", sa.String),
    sa.column("department", sa.String),
    sa.column("status", sa.String),
)
staff_permissions = sa.table(
    "staff_permissions",
    sa.column("staff_id", sa.String),
    sa.column("permission", sa.String),
)
staff_data_scopes = sa.table(
    "staff_data_scopes",
    sa.column("staff_id", sa.String),
    sa.column("scope_type", sa.String),
    sa.column("scope_value", sa.String),
)


class SqlPlatformRepository:
    """SQL adapter for the Staff/RBAC facts defined by the platform migration."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create_staff(self, staff: StaffAccount) -> None:
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    staff_accounts.insert().values(
                        id=staff.id,
                        employee_code=staff.employee_code,
                        department=staff.department,
                        status=staff.status.value,
                    )
                )
        except IntegrityError as exc:
            raise ValueError("employee_code already exists") from exc

    def staff(self, staff_id: str) -> StaffAccount | None:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(
                        staff_accounts.c.id,
                        staff_accounts.c.employee_code,
                        staff_accounts.c.department,
                        staff_accounts.c.status,
                    ).where(staff_accounts.c.id == staff_id)
                )
                .mappings()
                .one_or_none()
            )
        return _staff_from_row(row)

    def staff_for_employee_code(self, employee_code: str) -> StaffAccount | None:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(
                        staff_accounts.c.id,
                        staff_accounts.c.employee_code,
                        staff_accounts.c.department,
                        staff_accounts.c.status,
                    ).where(staff_accounts.c.employee_code == employee_code)
                )
                .mappings()
                .one_or_none()
            )
        return _staff_from_row(row)

    def has_employee_code(self, employee_code: str) -> bool:
        return self.staff_for_employee_code(employee_code) is not None

    def update_staff_status(self, staff_id: str, status: StaffStatus) -> StaffAccount:
        with self.engine.begin() as connection:
            result = connection.execute(
                staff_accounts.update()
                .where(staff_accounts.c.id == staff_id)
                .values(status=status.value)
            )
            if result.rowcount != 1:
                raise KeyError(staff_id)
        staff = self.staff(staff_id)
        if staff is None:
            raise KeyError(staff_id)
        return staff

    def grant_permission(self, permission: Permission) -> None:
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    staff_permissions.insert().values(
                        staff_id=permission.staff_id, permission=permission.name
                    )
                )
        except IntegrityError:
            return

    def grant_data_scope(self, scope: DataScope) -> None:
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    staff_data_scopes.insert().values(
                        staff_id=scope.staff_id,
                        scope_type=scope.scope_type,
                        scope_value=scope.scope_value,
                    )
                )
        except IntegrityError:
            return

    def permissions_for(self, staff_id: str) -> set[str]:
        with self.engine.begin() as connection:
            rows = connection.execute(
                sa.select(staff_permissions.c.permission).where(
                    staff_permissions.c.staff_id == staff_id
                )
            )
            return {str(row[0]) for row in rows}

    def scopes_for(self, staff_id: str) -> set[tuple[str, str]]:
        with self.engine.begin() as connection:
            rows = connection.execute(
                sa.select(staff_data_scopes.c.scope_type, staff_data_scopes.c.scope_value).where(
                    staff_data_scopes.c.staff_id == staff_id
                )
            )
            return {(str(row[0]), str(row[1])) for row in rows}


def _staff_from_row(row: sa.RowMapping | None) -> StaffAccount | None:
    if row is None:
        return None
    return StaffAccount(
        id=str(row["id"]),
        employee_code=str(row["employee_code"]),
        department=str(row["department"]),
        status=StaffStatus(str(row["status"])),
    )

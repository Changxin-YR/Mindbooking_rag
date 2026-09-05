import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4


class StaffStatus(StrEnum):
    PENDING_ACTIVATION = "PENDING_ACTIVATION"
    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"
    DISABLED = "DISABLED"
    OFFBOARDED = "OFFBOARDED"


@dataclass(frozen=True, slots=True)
class StaffAccount:
    id: str
    employee_code: str
    department: str
    status: StaffStatus = StaffStatus.ACTIVE
    platform_account_id: str | None = None

    @classmethod
    def create(cls, employee_code: str, department: str) -> StaffAccount:
        employee_code = employee_code.strip()
        department = department.strip()
        if not employee_code or not department:
            raise ValueError("employee_code and department are required")
        return cls(uuid4().hex, employee_code, department)


@dataclass(frozen=True, slots=True)
class Permission:
    staff_id: str
    name: str

    @classmethod
    def create(cls, staff_id: str, name: str) -> Permission:
        if re.fullmatch(r"[a-z][a-z0-9_.-]*\.[a-z][a-z0-9_.-]*", name) is None:
            raise ValueError("permission must use resource.action format")
        return cls(staff_id, name)


@dataclass(frozen=True, slots=True)
class DataScope:
    staff_id: str
    scope_type: str
    scope_value: str

    @classmethod
    def create(cls, staff_id: str, scope_type: str, scope_value: str) -> DataScope:
        if scope_type not in {
            "global",
            "department",
            "resource",
            "OWN",
            "TEAM",
            "DEPARTMENT",
            "ASSIGNED",
            "ALL",
            "CUSTOM",
        }:
            raise ValueError("unsupported data scope type")
        if not scope_value.strip():
            raise ValueError("scope_value is required")
        return cls(staff_id, scope_type, scope_value.strip())

from uuid import uuid4

from novel_platform.modules.legal.domain import LegalCase, LegalHold


class LegalService:
    def __init__(self) -> None:
        self.cases: dict[str, LegalCase] = {}
        self.holds: dict[str, LegalHold] = {}

    def open_case(self, subject: str) -> LegalCase:
        case = LegalCase(f"LGL_{uuid4().hex}", subject)
        self.cases[case.id] = case
        return case

    def hold(self, case_id: str, resource_id: str) -> LegalHold:
        if case_id not in self.cases:
            raise KeyError(case_id)
        item = LegalHold(f"HLD_{uuid4().hex}", case_id, resource_id)
        self.holds[item.id] = item
        return item

    def release(self, hold_id: str) -> LegalHold:
        item = self.holds[hold_id]
        item.status = "RELEASED"
        return item

    def is_held(self, resource_id: str) -> bool:
        return any(
            item.resource_id == resource_id and item.status == "ACTIVE"
            for item in self.holds.values()
        )

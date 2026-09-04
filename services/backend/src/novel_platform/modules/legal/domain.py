from dataclasses import dataclass


@dataclass(slots=True)
class LegalCase:
    id: str
    subject: str
    status: str = "OPEN"


@dataclass(slots=True)
class LegalHold:
    id: str
    case_id: str
    resource_id: str
    status: str = "ACTIVE"

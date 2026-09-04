from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RightItem:
    id: str
    dossier_id: str
    region: str
    language: str
    media: str
    exclusive: bool
    start_year: int
    end_year: int


@dataclass(slots=True)
class CopyrightDossier:
    id: str
    book_id: str
    right_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CopyrightComplaint:
    id: str
    book_id: str
    claimant_id: str
    reason: str
    evidence_ids: list[str] = field(default_factory=list)
    status: str = "SUBMITTED"
    counter_notice: str | None = None

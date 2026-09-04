from dataclasses import dataclass, field
from uuid import uuid4


class InvalidPenNameError(ValueError):
    pass


def normalize_pen_name(pen_name: str) -> str:
    normalized = " ".join(pen_name.split()).casefold()
    if not normalized or len(normalized) > 64:
        raise InvalidPenNameError("pen_name must contain 1 to 64 characters")
    return normalized


@dataclass(slots=True)
class AuthorProfile:
    id: str
    account_id: str
    pen_name: str
    normalized_pen_name: str
    pen_name_history: list[str] = field(default_factory=list)

    @classmethod
    def create(cls, account_id: str, pen_name: str) -> AuthorProfile:
        return cls(
            id=uuid4().hex,
            account_id=account_id,
            pen_name=pen_name.strip(),
            normalized_pen_name=normalize_pen_name(pen_name),
            pen_name_history=[pen_name.strip()],
        )

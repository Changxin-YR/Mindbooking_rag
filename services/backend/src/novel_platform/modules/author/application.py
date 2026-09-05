from dataclasses import dataclass

from novel_platform.modules.author.domain import (
    AuthorProfile,
    InvalidPenNameError,
    normalize_pen_name,
)
from novel_platform.modules.author.repository import AuthorRepository


class DuplicateAuthorProfileError(ValueError):
    pass


class DuplicatePenNameError(ValueError):
    pass


class AuthorProfileNotFoundError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class AuthorProfileResult:
    id: str
    account_id: str
    pen_name: str
    normalized_pen_name: str


class AuthorApplication:
    def __init__(self, repository: AuthorRepository) -> None:
        self.repository = repository

    def create_profile(self, account_id: str, pen_name: str) -> AuthorProfileResult:
        profile = AuthorProfile.create(account_id, pen_name)
        if self.repository.has_account_profile(account_id):
            raise DuplicateAuthorProfileError("account already has an author profile")
        if self.repository.has_pen_name(profile.normalized_pen_name):
            raise DuplicatePenNameError("pen name has already been used")
        try:
            self.repository.create_profile(profile)
        except ValueError as exc:
            raise DuplicatePenNameError("author uniqueness constraint violated") from exc
        return self._result(profile)

    def change_pen_name(self, profile_id: str, pen_name: str) -> AuthorProfileResult:
        profile = self.repository.profile(profile_id)
        if profile is None:
            raise AuthorProfileNotFoundError("author profile does not exist")
        normalized = normalize_pen_name(pen_name)
        if self.repository.has_pen_name(normalized):
            raise DuplicatePenNameError("pen name has already been used")
        try:
            self.repository.change_pen_name(profile_id, pen_name, normalized)
        except ValueError as exc:
            raise DuplicatePenNameError("pen name has already been used") from exc
        updated = self.repository.profile(profile_id)
        if updated is None:
            raise AuthorProfileNotFoundError("author profile does not exist")
        return self._result(updated)

    def account_id_for_profile(self, profile_id: str) -> str:
        profile = self.repository.profile(profile_id)
        if profile is None:
            raise AuthorProfileNotFoundError("author profile does not exist")
        return profile.account_id

    def profile_for_account(self, account_id: str) -> AuthorProfileResult:
        profile = self.repository.profile_for_account(account_id)
        if profile is None:
            raise AuthorProfileNotFoundError("author profile does not exist")
        return self._result(profile)

    def _result(self, profile: AuthorProfile) -> AuthorProfileResult:
        return AuthorProfileResult(
            profile.id, profile.account_id, profile.pen_name, profile.normalized_pen_name
        )


__all__ = [
    "AuthorApplication",
    "AuthorProfileNotFoundError",
    "AuthorProfileResult",
    "DuplicateAuthorProfileError",
    "DuplicatePenNameError",
    "InvalidPenNameError",
]

"""Staff-only authentication and authorization for the operations console."""

import base64
import binascii
import hashlib
import hmac
import json
import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import pbkdf2_hmac, sha256
from hmac import compare_digest
from secrets import token_bytes
from uuid import uuid4

import sqlalchemy as sa
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.engine import Engine

from novel_platform.core.auth import SessionClaims, SessionSigner
from novel_platform.core.http_auth import require_staff_session
from novel_platform.modules.platform.application import (
    AccessDeniedError,
    PlatformApplication,
    StaffNotFoundError,
)
from novel_platform.modules.platform.domain import StaffStatus


class InvalidStaffCredentialsError(ValueError):
    pass


class StaffMFARequired(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StaffAuthenticatedSession:
    staff_id: str
    token: str


class StaffAuthService:
    def __init__(
        self,
        platform: PlatformApplication,
        signer: SessionSigner,
        engine: Engine | None = None,
        mfa_encryption_key: str = "",
    ) -> None:
        self.platform = platform
        self.signer = signer
        self.engine = engine
        self._password_hashes: dict[str, str] = {}
        self._mfa_secrets: dict[str, str] = {}
        self._recovery_code_hashes: dict[str, set[str]] = {}
        self._mfa_audits: list[tuple[str, str, str]] = []
        self._mfa_cipher = (
            Fernet(base64.urlsafe_b64encode(sha256(mfa_encryption_key.encode()).digest()))
            if mfa_encryption_key
            else None
        )

    def set_password(self, staff_id: str, password: str) -> None:
        if len(password) < 12:
            raise ValueError("staff password must contain at least 12 characters")
        if self.platform.repository.staff(staff_id) is None:
            raise StaffNotFoundError("staff account does not exist")
        password_hash = _hash_password(password)
        if self.engine is None:
            self._password_hashes[staff_id] = password_hash
            return
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            exists = connection.execute(
                select(staff_credentials.c.staff_id).where(staff_credentials.c.staff_id == staff_id)
            ).scalar_one_or_none()
            if exists is None:
                connection.execute(
                    staff_credentials.insert().values(
                        staff_id=staff_id, password_hash=password_hash, updated_at=now
                    )
                )
            else:
                connection.execute(
                    staff_credentials.update()
                    .where(staff_credentials.c.staff_id == staff_id)
                    .values(password_hash=password_hash, updated_at=now)
                )

    def authenticate(
        self, employee_code: str, password: str, *, otp: str | None = None
    ) -> StaffAuthenticatedSession:
        staff = self.platform.staff_for_employee_code(employee_code)
        if self.engine is None:
            password_hash = self._password_hashes.get(staff.id)
        else:
            with self.engine.begin() as connection:
                password_hash = connection.execute(
                    select(staff_credentials.c.password_hash).where(
                        staff_credentials.c.staff_id == staff.id
                    )
                ).scalar_one_or_none()
        if (
            staff.status is not StaffStatus.ACTIVE
            or password_hash is None
            or not _verify_password(password, password_hash)
        ):
            raise InvalidStaffCredentialsError("invalid staff credentials")
        if self.requires_mfa(staff.id) or self.has_active_totp(staff.id):
            if otp is None:
                raise StaffMFARequired("staff MFA verification is required")
            if not self.verify_totp(staff.id, otp):
                raise InvalidStaffCredentialsError("invalid staff MFA code")
        token = self.signer.issue_staff(staff.id)
        if self.engine is not None:
            claims = self.signer.verify(token)
            if claims is None:
                raise InvalidStaffCredentialsError("could not create staff session")
            with self.engine.begin() as connection:
                connection.execute(
                    staff_sessions.insert().values(
                        id=claims.session_id,
                        staff_id=staff.id,
                        token_fingerprint=_fingerprint(token),
                        expires_at=datetime.fromtimestamp(claims.expires_at, UTC),
                        created_at=datetime.now(UTC),
                    )
                )
        return StaffAuthenticatedSession(staff.id, token)

    def enroll_totp(self, staff_id: str, secret: str | None = None) -> str:
        """Create or replace a staff TOTP factor and return its enrollment secret."""
        return self.enroll_totp_with_recovery(staff_id, secret=secret)[0]

    def enroll_totp_with_recovery(
        self,
        staff_id: str,
        secret: str | None = None,
        actor_staff_id: str | None = None,
    ) -> tuple[str, tuple[str, ...]]:
        """Create a factor and return plaintext recovery codes exactly once."""
        if self.platform.repository.staff(staff_id) is None:
            raise StaffNotFoundError("staff account does not exist")
        normalized = (secret or base64.b32encode(token_bytes(20)).decode("ascii")).rstrip("=")
        try:
            base64.b32decode(normalized + "=" * ((8 - len(normalized) % 8) % 8), casefold=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("invalid TOTP secret") from exc
        normalized = normalized.upper()
        recovery_codes = tuple(_recovery_code() for _ in range(8))
        recovery_hashes = {_hash_recovery_code(code) for code in recovery_codes}
        if self.engine is None:
            self._mfa_secrets[staff_id] = normalized
            self._recovery_code_hashes[staff_id] = recovery_hashes
        elif self._mfa_cipher is None:
            raise ValueError("staff MFA encryption key is required")
        if self.engine is not None:
            assert self._mfa_cipher is not None
            now = datetime.now(UTC)
            with self.engine.begin() as connection:
                connection.execute(
                    staff_mfa_factors.update()
                    .where(
                        staff_mfa_factors.c.staff_id == staff_id,
                        staff_mfa_factors.c.factor_type == "TOTP",
                        staff_mfa_factors.c.status == "ACTIVE",
                    )
                    .values(status="REVOKED")
                )
                factor_values: dict[str, object] = {
                    "id": f"MFA_{uuid4().hex}",
                    "staff_id": staff_id,
                    "factor_type": "TOTP",
                    "secret_ciphertext": self._mfa_cipher.encrypt(normalized.encode()).decode(),
                    "status": "ACTIVE",
                    "created_at": now,
                }
                if self._mfa_column_exists("recovery_codes_hash"):
                    factor_values["recovery_codes_hash"] = json.dumps(sorted(recovery_hashes))
                connection.execute(staff_mfa_factors.insert().values(**factor_values))
                self._write_mfa_audit(connection, staff_id, actor_staff_id or staff_id, "ENABLED")
        self._mfa_audits.append((staff_id, actor_staff_id or staff_id, "ENABLED"))
        return normalized, recovery_codes

    def disable_totp(self, staff_id: str, actor_staff_id: str) -> None:
        if self.platform.repository.staff(staff_id) is None:
            raise StaffNotFoundError("staff account does not exist")
        if self.engine is None:
            self._mfa_secrets.pop(staff_id, None)
            self._recovery_code_hashes.pop(staff_id, None)
            self._mfa_audits.append((staff_id, actor_staff_id, "DISABLED"))
            return
        with self.engine.begin() as connection:
            connection.execute(
                staff_mfa_factors.update()
                .where(
                    staff_mfa_factors.c.staff_id == staff_id,
                    staff_mfa_factors.c.factor_type == "TOTP",
                    staff_mfa_factors.c.status == "ACTIVE",
                )
                .values(status="REVOKED")
            )
            self._write_mfa_audit(connection, staff_id, actor_staff_id, "DISABLED")
        self._mfa_audits.append((staff_id, actor_staff_id, "DISABLED"))

    def requires_mfa(self, staff_id: str) -> bool:
        staff = self.platform.repository.staff(staff_id)
        if staff is None:
            return False
        department = staff.department.strip().lower().replace("-", "_")
        return department in {"finance", "risk", "admin", "security", "super_admin"}

    def has_active_totp(self, staff_id: str) -> bool:
        return self._totp_secret(staff_id) is not None

    def verify_totp(self, staff_id: str, code: str, *, now: datetime | None = None) -> bool:
        if len(code) != 6 or not code.isdecimal():
            return self._consume_recovery_code(staff_id, code)
        secret = self._totp_secret(staff_id)
        if secret is None:
            return False
        timestamp = int((now or datetime.now(UTC)).timestamp())
        counter = timestamp // 30
        return any(
            compare_digest(_totp_code(secret, counter + offset), code) for offset in (-1, 0, 1)
        )

    def _consume_recovery_code(self, staff_id: str, code: str) -> bool:
        if not code.strip():
            return False
        candidate = _hash_recovery_code(code.strip().upper())
        if self.engine is None:
            stored = self._recovery_code_hashes.get(staff_id, set())
            matched = next((value for value in stored if compare_digest(value, candidate)), None)
            if matched is None:
                return False
            stored.remove(matched)
            return True
        if not self._mfa_column_exists("recovery_codes_hash"):
            return False
        with self.engine.begin() as connection:
            row = connection.execute(
                select(staff_mfa_factors.c.recovery_codes_hash)
                .where(
                    staff_mfa_factors.c.staff_id == staff_id,
                    staff_mfa_factors.c.factor_type == "TOTP",
                    staff_mfa_factors.c.status == "ACTIVE",
                )
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                return False
            values = list(json.loads(str(row)))
            matched = next((value for value in values if compare_digest(value, candidate)), None)
            if matched is None:
                return False
            values.remove(matched)
            connection.execute(
                staff_mfa_factors.update()
                .where(
                    staff_mfa_factors.c.staff_id == staff_id,
                    staff_mfa_factors.c.factor_type == "TOTP",
                    staff_mfa_factors.c.status == "ACTIVE",
                )
                .values(recovery_codes_hash=json.dumps(values))
            )
            return True

    def _mfa_column_exists(self, name: str) -> bool:
        if self.engine is None:
            return True
        try:
            return any(
                str(column["name"]) == name
                for column in sa.inspect(self.engine).get_columns("staff_mfa_factors")
            )
        except sa.exc.NoSuchTableError:
            return False

    @staticmethod
    def _write_mfa_audit(
        connection: sa.Connection, staff_id: str, actor_staff_id: str, action: str
    ) -> None:
        if not sa.inspect(connection).has_table("staff_mfa_audits"):
            return
        connection.execute(
            sa.table(
                "staff_mfa_audits",
                sa.column("id", sa.String),
                sa.column("staff_id", sa.String),
                sa.column("action", sa.String),
                sa.column("actor_staff_id", sa.String),
                sa.column("created_at", sa.DateTime),
            )
            .insert()
            .values(
                id=f"MFA_AUDIT_{uuid4().hex}",
                staff_id=staff_id,
                action=action,
                actor_staff_id=actor_staff_id,
                created_at=datetime.now(UTC),
            )
        )

    def _totp_secret(self, staff_id: str) -> str | None:
        if self.engine is None:
            return self._mfa_secrets.get(staff_id)
        try:
            with self.engine.begin() as connection:
                encrypted = connection.execute(
                    select(staff_mfa_factors.c.secret_ciphertext).where(
                        staff_mfa_factors.c.staff_id == staff_id,
                        staff_mfa_factors.c.factor_type == "TOTP",
                        staff_mfa_factors.c.status == "ACTIVE",
                    )
                ).scalar_one_or_none()
        except sa.exc.OperationalError:
            # Older test schemas may not include the optional MFA table yet.
            return None
        if encrypted is None:
            return None
        if self._mfa_cipher is None:
            return None
        try:
            return self._mfa_cipher.decrypt(str(encrypted).encode()).decode()
        except InvalidToken:
            return None

    def verify(self, token: str) -> SessionClaims | None:
        claims = self.signer.verify(token)
        if claims is None or claims.subject_type != "STAFF":
            return None
        staff = self.platform.repository.staff(claims.account_id)
        if staff is None or staff.status is not StaffStatus.ACTIVE:
            return None
        if self.engine is not None:
            with self.engine.begin() as connection:
                row = (
                    connection.execute(
                        select(
                            staff_sessions.c.staff_id,
                            staff_sessions.c.token_fingerprint,
                            staff_sessions.c.expires_at,
                            staff_sessions.c.revoked_at,
                        ).where(staff_sessions.c.id == claims.session_id)
                    )
                    .mappings()
                    .one_or_none()
                )
            if row is None or row["staff_id"] != claims.account_id:
                return None
            expires_at = row["expires_at"]
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if row["token_fingerprint"] != _fingerprint(token) or row["revoked_at"] is not None:
                return None
            if expires_at <= datetime.now(UTC):
                return None
        return claims

    def authorize(
        self,
        claims: SessionClaims,
        permission: str,
        scope_type: str | None = None,
        scope_value: str | None = None,
    ) -> None:
        if claims.subject_type != "STAFF":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "PERMISSION_DENIED", "message": "staff actor required"},
            )
        if (scope_type is None) != (scope_value is None):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "PERMISSION_DENIED", "message": "complete data scope required"},
            )
        # Keep existing Admin callback compatibility, but never turn a scoped Staff into ALL.
        if scope_type is None:
            scope_type, scope_value = "ALL", "*"
        assert scope_value is not None
        try:
            self.platform.require_access(claims.account_id, permission, scope_type, scope_value)
        except (AccessDeniedError, StaffNotFoundError) as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "PERMISSION_DENIED", "message": str(exc)},
            ) from exc

    def authorize_permission(self, claims: SessionClaims, permission: str) -> None:
        if claims.subject_type != "STAFF":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "PERMISSION_DENIED", "message": "staff actor required"},
            )
        try:
            if not self.platform.has_permission(claims.account_id, permission):
                raise AccessDeniedError("staff lacks permission")
        except (AccessDeniedError, StaffNotFoundError) as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "PERMISSION_DENIED", "message": str(exc)},
            ) from exc

    def revoke(self, token: str) -> None:
        self.signer.revoke(token)
        if self.engine is not None:
            with self.engine.begin() as connection:
                connection.execute(
                    staff_sessions.update()
                    .where(staff_sessions.c.token_fingerprint == _fingerprint(token))
                    .values(revoked_at=datetime.now(UTC))
                )

    def revoke_all_for_staff(self, staff_id: str) -> None:
        if self.engine is not None:
            with self.engine.begin() as connection:
                connection.execute(
                    staff_sessions.update()
                    .where(
                        staff_sessions.c.staff_id == staff_id,
                        staff_sessions.c.revoked_at.is_(None),
                    )
                    .values(revoked_at=datetime.now(UTC))
                )


class StaffLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_code: str = Field(min_length=1)
    password: str = Field(min_length=1)
    # TOTP is six digits; recovery codes are one-time hexadecimal strings.
    otp: str | None = Field(default=None, min_length=6, max_length=64, pattern=r"^[A-Za-z0-9]+$")


class StaffSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: str
    access_token: str
    token_type: str = "Bearer"


class StaffPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=12)


class StaffMFAResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: str
    factor_type: str = "TOTP"
    secret: str
    recovery_codes: tuple[str, ...] = ()


def build_staff_auth_router(service: StaffAuthService) -> APIRouter:
    router = APIRouter(prefix="/admin/api/v1/auth/staff", tags=["staff-auth"])

    @router.post("/sessions", response_model=StaffSessionResponse)
    def create_session(payload: StaffLoginRequest) -> StaffSessionResponse:
        try:
            session = service.authenticate(payload.employee_code, payload.password, otp=payload.otp)
        except StaffMFARequired as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "MFA_REQUIRED",
                    "message": "staff MFA verification is required",
                },
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except (InvalidStaffCredentialsError, StaffNotFoundError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "INVALID_STAFF_CREDENTIALS",
                    "message": "Invalid staff credentials",
                },
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        return StaffSessionResponse(staff_id=session.staff_id, access_token=session.token)

    @router.delete("/sessions/current", status_code=status.HTTP_204_NO_CONTENT)
    def revoke_session(request: Request) -> Response:
        require_staff_session(request)
        service.revoke(getattr(request.state, "session_token", ""))
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/credentials/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
    def set_password(staff_id: str, payload: StaffPasswordRequest, request: Request) -> Response:
        claims = require_staff_session(request)
        service.authorize(claims, "platform.manage")
        try:
            service.set_password(staff_id, payload.password)
        except (StaffNotFoundError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/mfa/totp/{staff_id}", response_model=StaffMFAResponse)
    def enroll_totp(staff_id: str, request: Request) -> StaffMFAResponse:
        claims = require_staff_session(request)
        service.authorize(claims, "platform.manage")
        try:
            secret, recovery_codes = service.enroll_totp_with_recovery(
                staff_id, actor_staff_id=claims.account_id
            )
        except (StaffNotFoundError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        return StaffMFAResponse(staff_id=staff_id, secret=secret, recovery_codes=recovery_codes)

    @router.delete("/mfa/totp/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
    def disable_totp(staff_id: str, request: Request) -> Response:
        claims = require_staff_session(request)
        service.authorize(claims, "platform.manage")
        try:
            service.disable_totp(staff_id, claims.account_id)
        except (StaffNotFoundError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


def _hash_password(password: str) -> str:
    salt = token_bytes(16)
    iterations = 600_000
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, raw_iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(raw_iterations)
        )
        return compare_digest(actual, bytes.fromhex(digest_hex))
    except TypeError, ValueError:
        return False


staff_credentials = sa.table(
    "staff_credentials",
    sa.column("staff_id", sa.String),
    sa.column("password_hash", sa.String),
    sa.column("updated_at", sa.DateTime),
)
staff_sessions = sa.table(
    "staff_sessions",
    sa.column("id", sa.String),
    sa.column("staff_id", sa.String),
    sa.column("token_fingerprint", sa.String),
    sa.column("expires_at", sa.DateTime),
    sa.column("revoked_at", sa.DateTime),
    sa.column("created_at", sa.DateTime),
)
staff_mfa_factors = sa.table(
    "staff_mfa_factors",
    sa.column("id", sa.String),
    sa.column("staff_id", sa.String),
    sa.column("factor_type", sa.String),
    sa.column("secret_ciphertext", sa.String),
    sa.column("recovery_codes_hash", sa.Text),
    sa.column("status", sa.String),
    sa.column("created_at", sa.DateTime),
)


def _fingerprint(token: str) -> str:
    return sha256(token.encode("ascii", "ignore")).hexdigest()


def _recovery_code() -> str:
    return token_bytes(8).hex().upper()


def _hash_recovery_code(code: str) -> str:
    return sha256(code.encode("ascii")).hexdigest()


def _totp_code(secret: str, counter: int) -> str:
    raw_secret = base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8), casefold=True)
    digest = hmac.new(raw_secret, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return str(value).zfill(6)


__all__ = ["StaffAuthService", "StaffMFARequired", "build_staff_auth_router"]

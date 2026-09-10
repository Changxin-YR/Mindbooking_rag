"""HTTP authentication helpers shared by route adapters."""

from collections.abc import Callable

from fastapi import HTTPException, Request, status

from novel_platform.core.auth import SessionClaims, SessionSigner


def optional_session(request: Request) -> SessionClaims | None:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    signer = getattr(request.app.state, "session_signer", None)
    if not isinstance(signer, SessionSigner):
        return None
    normalized = token.strip()
    claims = signer.verify(normalized)
    if claims is not None:
        request.state.session_token = normalized
    return claims


def require_session(request: Request) -> SessionClaims:
    claims = optional_session(request)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTHENTICATION_REQUIRED", "message": "Bearer session required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    request.state.session = claims
    return claims


def require_staff_session(request: Request) -> SessionClaims:
    claims = getattr(request.state, "session", None)
    if not isinstance(claims, SessionClaims):
        # Route adapters can be mounted without PrivateApiMiddleware; parse the
        # bearer token here so `auth_required=True` remains a complete contract.
        claims = require_session(request)
    if claims.subject_type != "STAFF":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "STAFF_AUTHENTICATION_REQUIRED", "message": "Staff session required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    staff_auth = getattr(request.app.state, "staff_auth", None)
    verify = getattr(staff_auth, "verify", None)
    if callable(verify):
        verified = verify(getattr(request.state, "session_token", ""))
        if not isinstance(verified, SessionClaims) or verified.subject_type != "STAFF":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "STAFF_AUTHENTICATION_REQUIRED",
                    "message": "Staff session required",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        claims = verified
    return claims


def require_staff_authorization(
    request: Request,
    authorize_staff: Callable[[SessionClaims, str], None] | None,
    permission: str,
) -> SessionClaims:
    """Require a verified Staff session and an explicit authorization port."""
    claims = require_staff_session(request)
    if permission in getattr(request.state, "staff_authorized_permissions", set()):
        return claims
    if authorize_staff is None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "AUTHORIZATION_CONFIGURATION_ERROR",
                "message": "staff authorization callback is not configured",
            },
        )
    authorize_staff(claims, permission)
    return claims


def require_account_access(
    claims: SessionClaims | None, account_id: str, *, required: bool
) -> None:
    if not required:
        return
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTHENTICATION_REQUIRED", "message": "Bearer session required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    if claims.subject_type != "ACCOUNT" or claims.account_id != account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ACCOUNT_ACCESS_DENIED", "message": "account is not owned by session"},
        )

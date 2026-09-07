from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import optional_session, require_account_access, require_session
from novel_platform.modules.iam.application import (
    AccountAlreadyRealNamedError,
    AccountLoginNameTakenError,
    AccountNotFoundError,
    IdentityApplication,
    IdentityNotFoundError,
    InvalidCredentialsError,
    InvalidLoginNameError,
    InvalidNicknameError,
    RealNameSlotLimitError,
)
from novel_platform.modules.iam.domain import InvalidIdentityDocumentError, InvalidPhoneError


class CreateAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=1)
    password: str | None = Field(default=None, min_length=8)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=1)
    password: str = Field(min_length=1)


class SetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=8)


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    access_token: str
    token_type: str = "Bearer"


class AccountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    identity_id: str
    phone: str


class AccountProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    account_no: str
    status: str
    nickname: str | None = None
    login_name: str | None = None


class UpdateAccountProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nickname: str | None = Field(default=None, min_length=1, max_length=32)
    login_name: str | None = Field(default=None, min_length=3, max_length=32)


class AccountSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    status: str
    account_no: str
    nickname: str | None = None
    login_name: str | None = None


class PhoneAccountsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity_id: str
    phone: str
    default_account_id: str
    accounts: list[AccountSummary]


class RouteAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)


class RealNameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    identity_document: str = Field(min_length=18, max_length=18)


class RealNameResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    slot_status: str


def build_iam_router(application: IdentityApplication, *, auth_required: bool = False) -> APIRouter:
    router = APIRouter(tags=["iam"])

    @router.post(
        "/iam/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED
    )
    def create_account(payload: CreateAccountRequest) -> AccountResponse:
        try:
            result = application.register_phone_account(payload.phone, payload.password)
        except InvalidPhoneError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_PHONE", "message": str(exc)},
            ) from exc
        return AccountResponse(
            account_id=result.account_id,
            identity_id=result.identity_id,
            phone=result.phone,
        )

    @router.post("/iam/sessions", response_model=SessionResponse)
    def create_session(payload: LoginRequest) -> SessionResponse:
        try:
            session = application.authenticate_phone(payload.phone, payload.password)
        except (InvalidPhoneError, IdentityNotFoundError, InvalidCredentialsError) as exc:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_CREDENTIALS", "message": "Invalid credentials"},
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        return SessionResponse(account_id=session.account_id, access_token=session.token)

    @router.delete("/iam/sessions/current", status_code=status.HTTP_204_NO_CONTENT)
    def revoke_current_session(request: Request) -> Response:
        require_session(request)
        application.revoke_session(getattr(request.state, "session_token", ""))
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/iam/accounts/{account_id}/password", status_code=status.HTTP_204_NO_CONTENT)
    def set_password(
        account_id: str,
        payload: SetPasswordRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> Response:
        require_account_access(session, account_id, required=auth_required)
        try:
            application.set_password(account_id, payload.password)
        except (KeyError, ValueError) as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_PASSWORD", "message": str(exc)},
            ) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/iam/identities/phone/{phone}/accounts", response_model=PhoneAccountsResponse)
    def list_phone_accounts(
        phone: str,
        request: Request,
        session: SessionClaims | None = Depends(optional_session),
    ) -> PhoneAccountsResponse:
        try:
            identity = application._phone_identity(phone)
            accounts = application.accounts_for_phone(phone)
            default_account = application.default_account_for_phone(phone)
        except (InvalidPhoneError, IdentityNotFoundError) as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "IDENTITY_NOT_FOUND", "message": str(exc)},
            ) from exc
        if auth_required:
            claims = require_session(request)
            if claims.account_id not in {account.id for account in accounts}:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "IDENTITY_ACCESS_DENIED",
                        "message": "phone identity is not linked to account",
                    },
                )
        return PhoneAccountsResponse(
            identity_id=identity.id,
            phone=identity.normalized_value,
            default_account_id=default_account.id,
            accounts=[
                AccountSummary(
                    account_id=account.id,
                    status=account.status.value,
                    account_no=account.account_no,
                    nickname=account.nickname,
                    login_name=account.login_name,
                )
                for account in accounts
            ],
        )

    def account_profile_response(account_id: str) -> AccountProfileResponse:
        account = application.profile_for_account(account_id)
        return AccountProfileResponse(
            account_id=account.id,
            account_no=account.account_no,
            status=account.status.value,
            nickname=account.nickname,
            login_name=account.login_name,
        )

    @router.get(
        "/iam/accounts/{account_id}/profile",
        response_model=AccountProfileResponse,
        operation_id="get_account_profile",
    )
    def get_account_profile(
        account_id: str,
        session: SessionClaims | None = Depends(optional_session),
    ) -> AccountProfileResponse:
        require_account_access(session, account_id, required=auth_required)
        try:
            return account_profile_response(account_id)
        except AccountNotFoundError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "ACCOUNT_NOT_FOUND", "message": str(exc)},
            ) from exc

    @router.patch(
        "/iam/accounts/{account_id}/profile",
        response_model=AccountProfileResponse,
        operation_id="update_account_profile",
    )
    def update_account_profile(
        account_id: str,
        payload: UpdateAccountProfileRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> AccountProfileResponse:
        require_account_access(session, account_id, required=auth_required)
        if payload.nickname is None and payload.login_name is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "PROFILE_UPDATE_EMPTY", "message": "profile update is empty"},
            )
        try:
            account = application.update_profile(
                account_id, nickname=payload.nickname, login_name=payload.login_name
            )
        except AccountNotFoundError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "ACCOUNT_NOT_FOUND", "message": str(exc)},
            ) from exc
        except (InvalidNicknameError, InvalidLoginNameError) as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_PROFILE", "message": str(exc)},
            ) from exc
        except AccountLoginNameTakenError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={"code": "LOGIN_NAME_TAKEN", "message": str(exc)},
            ) from exc
        return AccountProfileResponse(
            account_id=account.id,
            account_no=account.account_no,
            status=account.status.value,
            nickname=account.nickname,
            login_name=account.login_name,
        )

    @router.post("/iam/identities/phone/{phone}/route", status_code=status.HTTP_204_NO_CONTENT)
    def route_phone_account(
        phone: str,
        payload: RouteAccountRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> Response:
        require_account_access(session, payload.account_id, required=auth_required)
        try:
            application.route_phone_to_account(phone, payload.account_id)
        except InvalidPhoneError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_PHONE", "message": str(exc)},
            ) from exc
        except (IdentityNotFoundError, AccountNotFoundError) as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "ACCOUNT_NOT_FOUND", "message": str(exc)},
            ) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post(
        "/iam/accounts/{account_id}/real-name",
        response_model=RealNameResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def verify_real_name(
        account_id: str,
        payload: RealNameRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> RealNameResponse:
        require_account_access(session, account_id, required=auth_required)
        try:
            link = application.verify_real_name(account_id, payload.name, payload.identity_document)
        except InvalidIdentityDocumentError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_IDENTITY_DOCUMENT", "message": str(exc)},
            ) from exc
        except RealNameSlotLimitError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={"code": "REAL_NAME_SLOT_LIMIT", "message": str(exc)},
            ) from exc
        except AccountAlreadyRealNamedError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={"code": "ACCOUNT_ALREADY_REAL_NAMED", "message": str(exc)},
            ) from exc
        return RealNameResponse(account_id=link.account_id, slot_status=link.slot_status.value)

    @router.get(
        "/iam/accounts/{account_id}/real-name",
        response_model=RealNameResponse,
        operation_id="get_real_name_status",
    )
    def real_name_status(
        account_id: str,
        session: SessionClaims | None = Depends(optional_session),
    ) -> RealNameResponse:
        require_account_access(session, account_id, required=auth_required)
        link = application.repository.real_name_link_for_account(account_id)
        return RealNameResponse(
            account_id=account_id,
            slot_status=link.slot_status.value if link is not None else "NOT_VERIFIED",
        )

    return router

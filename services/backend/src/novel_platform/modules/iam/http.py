from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.modules.iam.application import (
    AccountAlreadyRealNamedError,
    AccountNotFoundError,
    IdentityApplication,
    IdentityNotFoundError,
    RealNameSlotLimitError,
)
from novel_platform.modules.iam.domain import InvalidIdentityDocumentError, InvalidPhoneError


class CreateAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=1)


class AccountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    identity_id: str
    phone: str


class AccountSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    status: str


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


def build_iam_router(application: IdentityApplication) -> APIRouter:
    router = APIRouter(tags=["iam"])

    @router.post(
        "/iam/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED
    )
    def create_account(payload: CreateAccountRequest) -> AccountResponse:
        try:
            result = application.register_phone_account(payload.phone)
        except InvalidPhoneError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_PHONE", "message": str(exc)},
            ) from exc
        return AccountResponse(
            account_id=result.account_id, identity_id=result.identity_id, phone=result.phone
        )

    @router.get("/iam/identities/phone/{phone}/accounts", response_model=PhoneAccountsResponse)
    def list_phone_accounts(phone: str) -> PhoneAccountsResponse:
        try:
            identity = application._phone_identity(phone)
            accounts = application.accounts_for_phone(phone)
            default_account = application.default_account_for_phone(phone)
        except (InvalidPhoneError, IdentityNotFoundError) as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "IDENTITY_NOT_FOUND", "message": str(exc)},
            ) from exc
        return PhoneAccountsResponse(
            identity_id=identity.id,
            phone=identity.normalized_value,
            default_account_id=default_account.id,
            accounts=[
                AccountSummary(account_id=account.id, status=account.status.value)
                for account in accounts
            ],
        )

    @router.post("/iam/identities/phone/{phone}/route", status_code=status.HTTP_204_NO_CONTENT)
    def route_phone_account(phone: str, payload: RouteAccountRequest) -> Response:
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
    def verify_real_name(account_id: str, payload: RealNameRequest) -> RealNameResponse:
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

    return router

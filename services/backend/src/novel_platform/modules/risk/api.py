from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.modules.risk.application import RiskService
from novel_platform.modules.risk.domain import RiskSignalStatus


class ObserveSignalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    signal_type: str = Field(min_length=1)
    order_id: str = Field(min_length=1)


class RiskSignalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    account_id: str
    signal_type: str
    order_id: str
    status: RiskSignalStatus


class LoginSignalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    browser: str = Field(min_length=1)
    operating_system: str = Field(min_length=1)
    ip: str = Field(min_length=1)
    region: str = Field(min_length=1)
    user_agent: str = Field(min_length=1)


class WatchlistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_type: str = Field(min_length=1)
    target_value: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    case_id: str = Field(min_length=1)


class WatchlistReleaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)


def build_risk_router(service: RiskService) -> APIRouter:
    router = APIRouter(prefix="/admin/api/v1/risk", tags=["risk"])

    @router.post("/signals", response_model=RiskSignalResponse, status_code=status.HTTP_201_CREATED)
    def observe_signal(payload: ObserveSignalRequest) -> RiskSignalResponse:
        try:
            signal = service.observe(payload.account_id, payload.signal_type, payload.order_id)
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="order not found") from exc
        return RiskSignalResponse.model_validate(signal, from_attributes=True)

    @router.post("/signals/{signal_id}/freeze", response_model=RiskSignalResponse)
    def freeze_signal(signal_id: str) -> RiskSignalResponse:
        try:
            return RiskSignalResponse.model_validate(
                service.freeze(signal_id), from_attributes=True
            )
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="signal not found") from exc

    @router.post("/login-signals", status_code=status.HTTP_201_CREATED)
    def login_signal(payload: LoginSignalRequest) -> dict[str, object]:
        try:
            signal = service.record_login(**payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return (
            signal.__dict__
            if hasattr(signal, "__dict__")
            else {
                "id": signal.id,
                "account_id": signal.account_id,
                "device_id": signal.device_id,
                "browser": signal.browser,
                "operating_system": signal.operating_system,
                "ip": signal.ip,
                "region": signal.region,
                "user_agent": signal.user_agent,
                "status": signal.status,
            }
        )

    @router.post("/watchlist", status_code=status.HTTP_201_CREATED)
    def add_watchlist(payload: WatchlistRequest) -> dict[str, object]:
        try:
            entry = service.add_watchlist(**payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return {
            "id": entry.id,
            "target_type": entry.target_type,
            "target_value": entry.target_value,
            "reason": entry.reason,
            "case_id": entry.case_id,
            "status": entry.status,
        }

    @router.post("/watchlist/{entry_id}/release")
    def release_watchlist(entry_id: str, payload: WatchlistReleaseRequest) -> dict[str, object]:
        try:
            entry = service.release_watchlist(entry_id, **payload.model_dump())
        except KeyError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="watchlist entry not found"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return {
            "id": entry.id,
            "status": entry.status,
            "release_reason": entry.release_reason,
            "evidence_id": entry.evidence_id,
        }

    return router

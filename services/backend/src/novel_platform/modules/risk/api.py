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

    return router

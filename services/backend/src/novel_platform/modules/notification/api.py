from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.modules.notification.application import NotificationService
from novel_platform.modules.notification.domain import NotificationCategory, NotificationPriority


class SendNotificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    category: NotificationCategory
    priority: NotificationPriority
    channels: list[str] = Field(default_factory=list)


class MarketingPreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    enabled: bool


class NotificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    account_id: str
    category: NotificationCategory
    priority: NotificationPriority
    channels: list[str]


def build_notification_router(service: NotificationService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/notifications", tags=["notification"])

    @router.post("", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
    def send(payload: SendNotificationRequest) -> NotificationResponse:
        notification = service.send(
            payload.account_id, payload.category, payload.priority, payload.channels
        )
        return NotificationResponse(
            id=notification.id,
            account_id=notification.account_id,
            category=notification.category,
            priority=notification.priority,
            channels=sorted(notification.channels),
        )

    @router.put("/marketing-preference", status_code=status.HTTP_204_NO_CONTENT)
    def set_marketing_preference(payload: MarketingPreferenceRequest) -> None:
        try:
            service.set_marketing_enabled(payload.account_id, payload.enabled)
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return router

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from novel_platform.core.auth import SessionClaims
from novel_platform.core.http_auth import optional_session, require_account_access
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


class MarkReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)


class NotificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    account_id: str
    category: NotificationCategory
    priority: NotificationPriority
    channels: list[str]
    is_read: bool


def build_notification_router(
    service: NotificationService, *, auth_required: bool = False
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/notifications", tags=["notification"])

    @router.get("", response_model=list[NotificationResponse])
    def list_notifications(
        account_id: str,
        category: NotificationCategory | None = None,
        limit: int = 50,
        session: SessionClaims | None = Depends(optional_session),
    ) -> list[NotificationResponse]:
        require_account_access(session, account_id, required=auth_required)
        try:
            notifications = service.list(account_id, category=category, limit=limit)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return [
            NotificationResponse(
                id=item.id,
                account_id=item.account_id,
                category=item.category,
                priority=item.priority,
                channels=sorted(item.channels),
                is_read=item.is_read,
            )
            for item in notifications
        ]

    @router.get("/unread-count")
    def unread_count(
        account_id: str,
        session: SessionClaims | None = Depends(optional_session),
    ) -> dict[str, object]:
        require_account_access(session, account_id, required=auth_required)
        return {"account_id": account_id, "unread_count": service.unread_count(account_id)}

    @router.post("/{notification_id}/read", response_model=NotificationResponse)
    def mark_read(
        notification_id: str,
        payload: MarkReadRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> NotificationResponse:
        require_account_access(session, payload.account_id, required=auth_required)
        try:
            item = service.mark_read(payload.account_id, notification_id)
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="notification not found") from exc
        return NotificationResponse(
            id=item.id,
            account_id=item.account_id,
            category=item.category,
            priority=item.priority,
            channels=sorted(item.channels),
            is_read=item.is_read,
        )

    @router.post("", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
    def send(
        payload: SendNotificationRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> NotificationResponse:
        require_account_access(session, payload.account_id, required=auth_required)
        notification = service.send(
            payload.account_id, payload.category, payload.priority, payload.channels
        )
        return NotificationResponse(
            id=notification.id,
            account_id=notification.account_id,
            category=notification.category,
            priority=notification.priority,
            channels=sorted(notification.channels),
            is_read=notification.is_read,
        )

    @router.put("/marketing-preference", status_code=status.HTTP_204_NO_CONTENT)
    def set_marketing_preference(
        payload: MarketingPreferenceRequest,
        session: SessionClaims | None = Depends(optional_session),
    ) -> None:
        require_account_access(session, payload.account_id, required=auth_required)
        try:
            service.set_marketing_enabled(payload.account_id, payload.enabled)
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return router

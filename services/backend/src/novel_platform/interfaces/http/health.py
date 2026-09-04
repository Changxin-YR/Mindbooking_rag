from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from novel_platform.core.database import database_is_ready
from novel_platform.core.errors import ErrorResponse
from novel_platform.core.settings import Settings


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]


def build_health_router(surface: str) -> APIRouter:
    router = APIRouter(tags=["health"])
    router.add_api_route(
        "/health/live",
        live,
        methods=["GET"],
        response_model=HealthResponse,
        operation_id=f"{surface}_health_live",
    )
    router.add_api_route(
        "/health/ready",
        ready,
        methods=["GET"],
        response_model=HealthResponse,
        responses={503: {"model": ErrorResponse}},
        operation_id=f"{surface}_health_ready",
    )
    return router


async def live() -> HealthResponse:
    return HealthResponse(status="ok")


async def ready() -> HealthResponse:
    if not database_is_ready(Settings.from_env()):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "DEPENDENCY_UNAVAILABLE",
                "message": "Database is unavailable",
            },
        )
    return HealthResponse(status="ok")

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    permission: str = Field(min_length=1)
    read_only: bool = True
    high_risk: bool = False
    requires_confirmation: bool = False


class AgentToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    confirmation: bool = False
    session_id: str | None = None
    ip: str | None = None
    device_id: str | None = None


class AgentToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    data: Any


class AgentAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    agent_id: str
    actor_id: str
    tool_name: str
    permission: str
    outcome: str
    reason: str | None = None
    occurred_at: datetime
    session_id: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_summary: str | None = None
    ip: str | None = None
    device_id: str | None = None
    confirmed: bool = False
    risk_level: str = "LOW"

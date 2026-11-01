from typing import Any, Literal

from pydantic import BaseModel, Field


class SessionStartRequest(BaseModel):
    domain_id: str


class CodeEventRequest(BaseModel):
    session_id: str
    session_timestamp_ms: int = Field(ge=0)
    event_type: Literal["CODE_MUTATION", "HINT_USED"] = "CODE_MUTATION"
    data: dict[str, Any]


class SessionSubmitRequest(BaseModel):
    session_id: str
    duration_ms: int = Field(ge=0)
    hints_used: int = Field(default=0, ge=0)
    final_code: str = ""
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class RequestStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RetryAttempt(BaseModel):
    attempt: int
    delay_applied: float
    error: str | None = None
    latency_ms: float


class HandlerResult(BaseModel):
    status: str
    result: str | None = None
    error: str | None = None
    latency_ms: float
    attempts: list[RetryAttempt] = Field(default_factory=list)


class ProcessingRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    payload: dict
    status: RequestStatus = RequestStatus.PENDING
    degraded: bool = False
    degradation_reason: str | None = None
    primary_result: HandlerResult | None = None
    optional_result: HandlerResult | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None

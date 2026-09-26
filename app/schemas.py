from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain import ApplicationStatus


class EmailImport(BaseModel):
    external_id: str
    thread_id: str | None = None
    sender: str
    recipient: str | None = None
    subject: str = ""
    body_html: str | None = None
    body_text: str | None = None
    received_at: datetime
    labels: list[str] = Field(default_factory=list)


class ClassificationResult(BaseModel):
    is_relevant: bool
    status: ApplicationStatus
    confidence: float = Field(ge=0, le=1)
    provider: str
    evidence: list[str] = Field(default_factory=list)
    needs_review: bool = False
    company: str | None = None
    role: str | None = None
    summary: str = ""


class ApplicationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company: str
    role: str
    location: str | None
    current_status: str
    latest_update_at: datetime


class EventView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    occurred_at: datetime
    summary: str
    source: str
    confidence: float | None


class ApplicationDetail(ApplicationSummary):
    events: list[EventView]


class CorrectionRequest(BaseModel):
    status: ApplicationStatus
    company: str | None = None
    role: str | None = None
    note: str | None = None

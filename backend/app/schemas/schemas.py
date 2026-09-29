from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class IncidentCreate(BaseModel):
    service_name: str
    environment: str = "production"
    severity: str = "SEV-2"
    symptoms: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)  # e.g. {"error_rate": 18.4, "latency_ms": 2400, "db_connections_pct": 96}
    recent_deployment: Optional[dict] = None  # {"version": "v2.4.1", "changes": "...", "minutes_before": 8}
    affected_component: Optional[str] = None  # e.g. "checkout-service pod checkout-7b4df" or an endpoint/host


class DeploymentOut(BaseModel):
    id: int
    version: str
    timestamp: datetime
    changes: str
    status: str
    minutes_before_incident: Optional[float] = None

    class Config:
        from_attributes = True


class OutcomeOut(BaseModel):
    id: int
    status: str
    metrics_before: dict
    metrics_after: dict
    duration_minutes: Optional[int]
    notes: str

    class Config:
        from_attributes = True


class ActionOut(BaseModel):
    id: int
    incident_id: int
    type: str
    description: str
    timestamp: datetime
    approved_by: Optional[str]
    status: str
    recommendation: Optional[dict] = None
    outcome: Optional[OutcomeOut] = None

    class Config:
        from_attributes = True


class LessonOut(BaseModel):
    id: int
    lesson_text: str
    evidence: list
    created_at: datetime

    class Config:
        from_attributes = True


class IncidentOut(BaseModel):
    id: int
    service_name: str
    environment: str
    severity: str
    timestamp: datetime
    symptoms: list
    status: str
    root_cause: Optional[str]
    affected_component: Optional[str] = None
    metrics_before: dict
    metrics_after: Optional[dict]
    resolution: Optional[str]
    actions: list[ActionOut] = Field(default_factory=list)
    lessons: list[LessonOut] = Field(default_factory=list)
    recent_deployment: Optional[DeploymentOut] = None

    class Config:
        from_attributes = True


class SimilarIncidentOut(BaseModel):
    incident_id: int
    service_name: str
    similarity_score: int  # 0-100
    severity: str
    symptoms: list
    root_cause: Optional[str]
    key_lesson: Optional[str]
    actions: list[ActionOut] = Field(default_factory=list)


class ConfidenceBreakdownItem(BaseModel):
    signal: str
    weight: int
    matched: bool
    contribution: int
    explanation: str


class RecommendationOut(BaseModel):
    incident_id: int
    recommended_action: str
    target: str
    reason: str
    evidence: list[str]
    warnings: list[str]
    alternative_actions: list[str]
    risk: str
    confidence: int
    confidence_breakdown: list[ConfidenceBreakdownItem]
    source: str  # "llm" or "deterministic_fallback"
    action_id: int


class ApprovalRequest(BaseModel):
    approved_by: str = "on-call-engineer"


class TimelineEvent(BaseModel):
    label: str
    timestamp: Optional[datetime]
    detail: str


class HealthOut(BaseModel):
    status: str
    llm_configured: bool
    hindsight_configured: bool

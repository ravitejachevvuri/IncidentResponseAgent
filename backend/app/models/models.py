import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    JSON,
    Text,
)
from sqlalchemy.orm import relationship

from app.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class Severity(str, enum.Enum):
    SEV1 = "SEV-1"
    SEV2 = "SEV-2"
    SEV3 = "SEV-3"


class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"


class ActionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SIMULATED = "simulated"


class OutcomeStatus(str, enum.Enum):
    SUCCESSFUL = "successful"
    PARTIAL = "partial"
    TEMPORARY = "temporary"
    FAILED = "failed"
    UNRESOLVED = "unresolved"


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    environment = Column(String, default="production")
    owner = Column(String, default="platform-team")

    incidents = relationship("Incident", back_populates="service")
    deployments = relationship("Deployment", back_populates="service")


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(Integer, primary_key=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    version = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=utcnow)
    changes = Column(Text, default="")
    status = Column(String, default="deployed")

    service = relationship("Service", back_populates="deployments")


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    severity = Column(String, default=Severity.SEV2.value)
    timestamp = Column(DateTime(timezone=True), default=utcnow)
    symptoms = Column(JSON, default=list)  # list[str]
    status = Column(String, default=IncidentStatus.OPEN.value)
    root_cause = Column(Text, nullable=True)
    affected_component = Column(String, nullable=True)  # e.g. an endpoint, host, or pod name
    metrics_before = Column(JSON, default=dict)
    metrics_after = Column(JSON, nullable=True)
    resolution = Column(Text, nullable=True)
    is_historical = Column(Integer, default=0)  # 1 = seeded historical incident used only as memory
    recent_deployment_id = Column(Integer, ForeignKey("deployments.id"), nullable=True)

    service = relationship("Service", back_populates="incidents")
    actions = relationship("Action", back_populates="incident", cascade="all, delete-orphan")
    lessons = relationship("Lesson", back_populates="incident", cascade="all, delete-orphan")
    recent_deployment = relationship("Deployment", foreign_keys=[recent_deployment_id])
    embedding = relationship(
        "IncidentEmbedding", back_populates="incident", uselist=False, cascade="all, delete-orphan"
    )


class Action(Base):
    __tablename__ = "actions"

    id = Column(Integer, primary_key=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)
    type = Column(String, nullable=False)  # e.g. rollback_deployment, restart_service
    description = Column(Text, default="")
    timestamp = Column(DateTime(timezone=True), default=utcnow)
    approved_by = Column(String, nullable=True)
    status = Column(String, default=ActionStatus.PENDING.value)
    recommendation = Column(JSON, nullable=True)  # full recommendation JSON contract, when AI-generated

    incident = relationship("Incident", back_populates="actions")
    outcome = relationship("Outcome", back_populates="action", uselist=False, cascade="all, delete-orphan")


class Outcome(Base):
    __tablename__ = "outcomes"

    id = Column(Integer, primary_key=True)
    action_id = Column(Integer, ForeignKey("actions.id"), nullable=False)
    status = Column(String, default=OutcomeStatus.UNRESOLVED.value)
    metrics_before = Column(JSON, default=dict)
    metrics_after = Column(JSON, default=dict)
    duration_minutes = Column(Integer, nullable=True)
    notes = Column(Text, default="")

    action = relationship("Action", back_populates="outcome")


class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)
    lesson_text = Column(Text, nullable=False)
    evidence = Column(JSON, default=list)  # list[str] incident/action ids referenced
    created_at = Column(DateTime(timezone=True), default=utcnow)

    incident = relationship("Incident", back_populates="lessons")


class IncidentEmbedding(Base):
    __tablename__ = "incident_embeddings"

    incident_id = Column(Integer, ForeignKey("incidents.id"), primary_key=True)
    vector = Column(JSON, nullable=False)  # list[float]; cosine-compared in app code

    incident = relationship("Incident", back_populates="embedding")

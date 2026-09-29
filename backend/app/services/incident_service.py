from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.models import Service, Incident, Deployment, IncidentEmbedding
from app.schemas.schemas import IncidentCreate
from app.services.similarity_service import RECENT_DEPLOYMENT_WINDOW_MINUTES
from app.ai.embeddings import embed_incident


def incident_code(incident_id: int) -> str:
    return f"INC-{incident_id:03d}"


def build_timeline(db: Session, incident: Incident) -> list[dict]:
    events = []
    deployment = get_incident_deployment(db, incident)
    if deployment:
        events.append(
            {
                "label": "Deployment",
                "timestamp": deployment.timestamp,
                "detail": f"{deployment.version} deployed ({deployment.changes})",
            }
        )
    events.append(
        {
            "label": "Detection",
            "timestamp": incident.timestamp,
            "detail": f"Incident detected: {', '.join(incident.symptoms) or 'symptoms recorded'}",
        }
    )
    for action in sorted(incident.actions, key=lambda a: a.timestamp):
        rec = action.recommendation or {}
        events.append(
            {
                "label": "Recommendation",
                "timestamp": action.timestamp,
                "detail": f"Recommended {action.type} (confidence {rec.get('confidence', '?')}%, source={rec.get('source', 'n/a')})",
            }
        )
        if action.status.value if hasattr(action.status, "value") else action.status:
            status = action.status.value if hasattr(action.status, "value") else action.status
            if status in ("approved", "simulated", "rejected"):
                events.append(
                    {
                        "label": "Action " + status,
                        "timestamp": action.timestamp,
                        "detail": f"{action.type} was {status} by {action.approved_by or 'n/a'}",
                    }
                )
        if action.outcome:
            events.append(
                {
                    "label": "Outcome",
                    "timestamp": action.timestamp,
                    "detail": f"Outcome: {action.outcome.status.value if hasattr(action.outcome.status, 'value') else action.outcome.status} — {action.outcome.notes}",
                }
            )
    if incident.status.value if hasattr(incident.status, "value") else incident.status:
        status = incident.status.value if hasattr(incident.status, "value") else incident.status
        if status == "resolved":
            events.append(
                {
                    "label": "Resolution",
                    "timestamp": incident.timestamp,
                    "detail": incident.resolution or "Incident resolved.",
                }
            )
    return events


def get_or_create_service(db: Session, name: str, environment: str) -> Service:
    service = db.query(Service).filter(Service.name == name).first()
    if service:
        return service
    service = Service(name=name, environment=environment)
    db.add(service)
    db.flush()
    return service


def get_recent_deployment(db: Session, service_id: int, before: datetime) -> Deployment | None:
    """Window-based heuristic: 'whatever's most recent for this service before this
    timestamp'. Only used as a fallback for incidents with no explicit deployment link
    (seeded historical incidents). Live incidents should use get_incident_deployment()
    instead - this heuristic can drift and attribute the wrong deployment once multiple
    incidents/deployments exist close together on the same service."""
    if before.tzinfo is None:
        before = before.replace(tzinfo=timezone.utc)
    window_start = before - timedelta(minutes=RECENT_DEPLOYMENT_WINDOW_MINUTES)
    return (
        db.query(Deployment)
        .filter(
            Deployment.service_id == service_id,
            Deployment.timestamp <= before,
            Deployment.timestamp >= window_start,
            Deployment.status == "deployed",
        )
        .order_by(Deployment.timestamp.desc())
        .first()
    )


def get_incident_deployment(db: Session, incident: Incident) -> Deployment | None:
    """The deployment actually tied to this incident. Uses the explicit FK captured at
    creation time when available (unambiguous); falls back to the window heuristic only
    for incidents that predate/lack that link."""
    if incident.recent_deployment_id:
        deployment = db.query(Deployment).get(incident.recent_deployment_id)
        if deployment and deployment.status == "deployed":
            return deployment
        return None
    return get_recent_deployment(db, incident.service_id, incident.timestamp)


def create_incident(db: Session, payload: IncidentCreate) -> Incident:
    service = get_or_create_service(db, payload.service_name, payload.environment)
    incident_timestamp = datetime.now(timezone.utc)
    incident = Incident(
        service_id=service.id,
        severity=payload.severity,
        symptoms=payload.symptoms,
        metrics_before=payload.metrics,
        timestamp=incident_timestamp,
        affected_component=payload.affected_component,
    )
    db.add(incident)
    db.flush()

    if payload.recent_deployment:
        minutes_before = payload.recent_deployment.get("minutes_before", 5)
        deployment = Deployment(
            service_id=service.id,
            version=payload.recent_deployment.get("version", "unknown"),
            timestamp=incident_timestamp - timedelta(minutes=minutes_before),
            changes=payload.recent_deployment.get("changes", ""),
            status="deployed",
        )
        db.add(deployment)
        db.flush()
        incident.recent_deployment_id = deployment.id

    embedding = IncidentEmbedding(
        incident_id=incident.id, vector=embed_incident(payload.symptoms, None)
    )
    db.add(embedding)
    db.commit()
    db.refresh(incident)
    return incident


def minutes_before_incident(deployment: Deployment, incident: Incident) -> float:
    ts = incident.timestamp
    dts = deployment.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if dts.tzinfo is None:
        dts = dts.replace(tzinfo=timezone.utc)
    return round((ts - dts).total_seconds() / 60, 1)


def serialize_incident(db: Session, incident: Incident) -> dict:
    service = db.query(Service).get(incident.service_id)
    deployment = get_incident_deployment(db, incident)
    recent_deployment = None
    if deployment:
        recent_deployment = {
            "id": deployment.id,
            "version": deployment.version,
            "timestamp": deployment.timestamp,
            "changes": deployment.changes,
            "status": deployment.status,
            "minutes_before_incident": minutes_before_incident(deployment, incident),
        }
    return {
        "id": incident.id,
        "service_name": service.name,
        "environment": service.environment,
        "severity": incident.severity.value
        if hasattr(incident.severity, "value")
        else incident.severity,
        "timestamp": incident.timestamp,
        "symptoms": incident.symptoms,
        "status": incident.status.value if hasattr(incident.status, "value") else incident.status,
        "root_cause": incident.root_cause,
        "affected_component": incident.affected_component,
        "metrics_before": incident.metrics_before,
        "metrics_after": incident.metrics_after,
        "resolution": incident.resolution,
        "actions": [serialize_action(a) for a in incident.actions],
        "lessons": [
            {
                "id": l.id,
                "lesson_text": l.lesson_text,
                "evidence": l.evidence,
                "created_at": l.created_at,
            }
            for l in incident.lessons
        ],
        "recent_deployment": recent_deployment,
    }


def serialize_action(action) -> dict:
    outcome = None
    if action.outcome:
        outcome = {
            "id": action.outcome.id,
            "status": action.outcome.status.value
            if hasattr(action.outcome.status, "value")
            else action.outcome.status,
            "metrics_before": action.outcome.metrics_before,
            "metrics_after": action.outcome.metrics_after,
            "duration_minutes": action.outcome.duration_minutes,
            "notes": action.outcome.notes,
        }
    return {
        "id": action.id,
        "incident_id": action.incident_id,
        "type": action.type,
        "description": action.description,
        "timestamp": action.timestamp,
        "approved_by": action.approved_by,
        "status": action.status.value if hasattr(action.status, "value") else action.status,
        "recommendation": action.recommendation,
        "outcome": outcome,
    }

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.config import settings
from app.models.models import Incident, Action, Service, Deployment
from app.schemas.schemas import IncidentCreate, ApprovalRequest, HealthOut
from app.services import incident_service, memory_service, recommendation_service, outcome_service
from app.services.incident_service import incident_code
from app.ai import hindsight_memory

router = APIRouter(prefix="/api")


def _get_incident(db: Session, incident_id: int) -> Incident:
    incident = db.query(Incident).get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


def _get_action(db: Session, action_id: int) -> Action:
    action = db.query(Action).get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    return action


@router.get("/health", response_model=HealthOut)
def health():
    return {
        "status": "ok",
        "llm_configured": bool(settings.groq_api_key),
        "hindsight_configured": hindsight_memory.is_configured(),
    }


@router.post("/incidents")
def create_incident(payload: IncidentCreate, db: Session = Depends(get_db)):
    incident = incident_service.create_incident(db, payload)
    return incident_service.serialize_incident(db, incident)


@router.get("/incidents/history")
def incident_history(db: Session = Depends(get_db)):
    incidents = db.query(Incident).order_by(Incident.timestamp.desc()).all()
    return [
        {
            **incident_service.serialize_incident(db, incident),
            "code": incident_code(incident.id),
        }
        for incident in incidents
    ]


@router.get("/deployments")
def list_deployments(db: Session = Depends(get_db)):
    deployments = db.query(Deployment).order_by(Deployment.timestamp.desc()).all()
    return [
        {
            "id": d.id,
            "service_name": d.service.name,
            "version": d.version,
            "timestamp": d.timestamp,
            "changes": d.changes,
            "status": d.status,
        }
        for d in deployments
    ]


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: int, db: Session = Depends(get_db)):
    incident = _get_incident(db, incident_id)
    return {**incident_service.serialize_incident(db, incident), "code": incident_code(incident.id)}


@router.get("/incidents/{incident_id}/similar")
def similar_incidents(incident_id: int, db: Session = Depends(get_db)):
    incident = _get_incident(db, incident_id)
    return memory_service.get_similar_incidents(db, incident)


@router.post("/incidents/{incident_id}/recommendation")
def create_recommendation(incident_id: int, db: Session = Depends(get_db)):
    incident = _get_incident(db, incident_id)
    return recommendation_service.generate_recommendation(db, incident)


@router.get("/incidents/{incident_id}/timeline")
def timeline(incident_id: int, db: Session = Depends(get_db)):
    incident = _get_incident(db, incident_id)
    return incident_service.build_timeline(db, incident)


@router.post("/actions/{action_id}/approve")
def approve_action(action_id: int, payload: ApprovalRequest, db: Session = Depends(get_db)):
    action = _get_action(db, action_id)
    action = outcome_service.approve_action(db, action, payload.approved_by)
    return incident_service.serialize_action(action)


@router.post("/actions/{action_id}/reject")
def reject_action(action_id: int, payload: ApprovalRequest, db: Session = Depends(get_db)):
    action = _get_action(db, action_id)
    action = outcome_service.reject_action(db, action, payload.approved_by)
    return incident_service.serialize_action(action)


@router.post("/actions/{action_id}/simulate")
def simulate_action(action_id: int, db: Session = Depends(get_db)):
    action = _get_action(db, action_id)
    if action.status not in ("approved",):
        raise HTTPException(status_code=400, detail="Action must be approved before simulation")
    return outcome_service.run_simulation(db, action)


@router.post("/actions/{action_id}/outcome")
def record_outcome(action_id: int, db: Session = Depends(get_db)):
    action = _get_action(db, action_id)
    sim = (action.recommendation or {}).get("_simulation")
    if sim:
        metrics_after, regresses = sim["metrics_after"], sim["regresses_after_minutes"]
    else:
        result = outcome_service.run_simulation(db, action)
        metrics_after, regresses = result["metrics_after"], result["regresses_after_minutes"]
    outcome = outcome_service.record_outcome(db, action, metrics_after, regresses)
    return {
        "id": outcome.id,
        "status": outcome.status.value if hasattr(outcome.status, "value") else outcome.status,
        "metrics_before": outcome.metrics_before,
        "metrics_after": outcome.metrics_after,
        "duration_minutes": outcome.duration_minutes,
        "notes": outcome.notes,
        "incident": incident_service.serialize_incident(db, action.incident),
    }


@router.post("/demo/reset")
def reset_demo(db: Session = Depends(get_db)):
    from seed.seed_data import reset_and_seed

    reset_and_seed(db)
    return {"status": "reset"}

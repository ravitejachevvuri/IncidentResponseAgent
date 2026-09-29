from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import Action, ActionStatus, Outcome, OutcomeStatus, Incident, IncidentStatus, Lesson
from app.services.similarity_service import NORMAL_RANGES
from app.services.simulation_service import simulate_action
from app.services.recommendation_service import ACTION_LABELS
from app.services.incident_service import incident_code, get_incident_deployment
from app.ai import hindsight_memory


def approve_action(db: Session, action: Action, approved_by: str) -> Action:
    action.status = ActionStatus.APPROVED.value
    action.approved_by = approved_by
    db.commit()
    db.refresh(action)
    return action


def reject_action(db: Session, action: Action, approved_by: str) -> Action:
    action.status = ActionStatus.REJECTED.value
    action.approved_by = approved_by
    db.commit()
    db.refresh(action)
    return action


def _improvement_ratio(before: dict, after: dict) -> float:
    ratios = []
    for key in NORMAL_RANGES:
        if before.get(key) and key in after:
            ratios.append(max(0.0, min(1.0, (before[key] - after[key]) / before[key])))
    return sum(ratios) / len(ratios) if ratios else 0.0


def _within_normal(metrics: dict) -> bool:
    return all(metrics.get(key, 0) <= threshold for key, threshold in NORMAL_RANGES.items() if key in metrics)


def classify_outcome(
    action_type: str, metrics_before: dict, metrics_after: dict, regresses_after_minutes: int | None
) -> tuple[str, str]:
    if action_type == "no_action":
        return (
            OutcomeStatus.UNRESOLVED.value,
            "No remediation was executed; incident remains open pending manual investigation.",
        )
    if regresses_after_minutes:
        return (
            OutcomeStatus.TEMPORARY.value,
            f"Metrics improved immediately but regressed after ~{regresses_after_minutes} minutes, "
            "consistent with the historical pattern for this action.",
        )
    if _within_normal(metrics_after):
        return OutcomeStatus.SUCCESSFUL.value, "All key metrics returned to within normal operating range."

    ratio = _improvement_ratio(metrics_before, metrics_after)
    if ratio >= 0.4:
        return (
            OutcomeStatus.PARTIAL.value,
            "Metrics improved meaningfully but at least one signal remains outside normal range; "
            "the underlying cause may not be fully resolved.",
        )
    if ratio > 0.1:
        return OutcomeStatus.PARTIAL.value, "Metrics improved slightly; further investigation is recommended."
    return OutcomeStatus.FAILED.value, "Metrics did not meaningfully improve after the action."


def run_simulation(db: Session, action: Action) -> dict:
    incident: Incident = action.incident
    metrics_after, regresses_after_minutes = simulate_action(action.type, incident.metrics_before)
    action.status = ActionStatus.SIMULATED.value
    recommendation = dict(action.recommendation or {})
    recommendation["_simulation"] = {
        "metrics_after": metrics_after,
        "regresses_after_minutes": regresses_after_minutes,
    }
    action.recommendation = recommendation
    db.commit()
    return {
        "metrics_before": incident.metrics_before,
        "metrics_after": metrics_after,
        "regresses_after_minutes": regresses_after_minutes,
    }


def record_outcome(db: Session, action: Action, metrics_after: dict, regresses_after_minutes: int | None) -> Outcome:
    incident: Incident = action.incident
    status, notes = classify_outcome(action.type, incident.metrics_before, metrics_after, regresses_after_minutes)

    outcome = Outcome(
        action_id=action.id,
        status=status,
        metrics_before=incident.metrics_before,
        metrics_after=metrics_after,
        duration_minutes=regresses_after_minutes,
        notes=notes,
    )
    db.add(outcome)

    incident.metrics_after = metrics_after
    if status == OutcomeStatus.SUCCESSFUL.value:
        incident.status = IncidentStatus.RESOLVED.value
        incident.resolution = f"Resolved via {ACTION_LABELS.get(action.type, action.type).lower()}."
        incident.root_cause = incident.root_cause or _infer_root_cause(action.type)
        if action.type == "rollback_deployment":
            deployment = get_incident_deployment(db, incident)
            if deployment:
                deployment.status = "rolled_back"
    elif status in (OutcomeStatus.PARTIAL.value, OutcomeStatus.TEMPORARY.value):
        incident.status = IncidentStatus.INVESTIGATING.value
    db.flush()

    lesson_text = _generate_lesson(action, status, notes)
    lesson = Lesson(
        incident_id=incident.id,
        lesson_text=lesson_text,
        evidence=[incident_code(incident.id)],
    )
    db.add(lesson)
    db.commit()
    db.refresh(outcome)

    service_name = incident.service.name
    hindsight_memory.retain_incident_memory(
        service_name=service_name,
        content=(
            f"Incident {incident_code(incident.id)} on {service_name}: symptoms were "
            f"{', '.join(incident.symptoms)}. "
            + (f"Affected component: {incident.affected_component}. " if incident.affected_component else "")
            + f"Root cause: {incident.root_cause}. "
            f"Action taken: {action.description} ({action.type}). Outcome: {status} — {notes} "
            f"Lesson: {lesson_text}"
        ),
        metadata={
            "incident_code": incident_code(incident.id),
            "service": service_name,
            "action_type": action.type,
            "outcome_status": status,
            "severity": incident.severity,
        },
        tags=[action.type, status],
    )

    return outcome


def _infer_root_cause(action_type: str) -> str:
    return {
        "rollback_deployment": "Recent deployment introduced a regression (deployment-related root cause).",
        "restart_service": "Transient resource exhaustion; underlying cause not addressed by restart alone.",
        "increase_connection_pool": "Connection pool sizing was insufficient for current load.",
        "inspect_db_connections": "Long-running queries or a connection leak saturating the database.",
        "investigate_query_performance": "Inefficient query pattern under current load.",
        "scale_service": "Service was under-provisioned for current traffic.",
        "rotate_credentials": "An expired credential, token, or certificate caused authentication failures.",
        "adjust_timeout_and_retries": "Downstream dependency latency exceeded the configured timeout window.",
    }.get(action_type, "Root cause not fully determined.")


def _generate_lesson(action: Action, status: str, notes: str) -> str:
    label = ACTION_LABELS.get(action.type, action.type)
    if status == OutcomeStatus.SUCCESSFUL.value:
        return f"{label} was effective for this incident pattern. {notes}"
    if status == OutcomeStatus.TEMPORARY.value:
        return f"{label} only provided temporary relief for this incident pattern. {notes} Do not rely on it as a permanent fix next time."
    if status == OutcomeStatus.PARTIAL.value:
        return f"{label} partially mitigated the incident but did not fully resolve it. {notes}"
    if status == OutcomeStatus.FAILED.value:
        return f"{label} did not resolve this incident pattern. {notes} Consider a different action for similar future incidents."
    return f"No automated action was taken. {notes}"

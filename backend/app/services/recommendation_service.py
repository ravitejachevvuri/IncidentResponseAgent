import json
import re

from sqlalchemy.orm import Session

from app.models.models import Incident, Action, ActionStatus
from app.services.incident_service import get_incident_deployment, incident_code, minutes_before_incident
from app.services.memory_service import get_similar_incidents
from app.services.similarity_service import symptom_similarity, metric_similarity
from app.ai.llm_client import generate_recommendation as llm_generate
from app.ai import hindsight_memory
from app.ai.prompts import ALLOWED_ACTIONS

ACTION_LABELS = {
    "rollback_deployment": "Rollback deployment",
    "restart_service": "Restart service",
    "increase_connection_pool": "Increase connection pool",
    "inspect_db_connections": "Inspect DB connections",
    "scale_service": "Scale service",
    "investigate_query_performance": "Investigate query performance",
    "rotate_credentials": "Rotate credentials",
    "adjust_timeout_and_retries": "Adjust timeout and retries",
    "no_action": "Manual investigation (no automated action)",
}

DB_SIGNAL_KEYS = ("db_connections_pct", "db_connections")
INCIDENT_CODE_RE = re.compile(r"INC-\d+")


def _has_db_signal(metrics: dict) -> bool:
    for key in DB_SIGNAL_KEYS:
        if metrics.get(key, 0) and float(metrics[key]) >= 80:
            return True
    return False


def build_reasoning_context(db: Session, incident: Incident) -> dict:
    deployment = get_incident_deployment(db, incident)
    similar = get_similar_incidents(db, incident)

    current = {
        "service": incident.service.name,
        "severity": incident.severity.value if hasattr(incident.severity, "value") else incident.severity,
        "symptoms": incident.symptoms,
        "metrics": incident.metrics_before,
        "has_recent_deployment": deployment is not None,
    }

    recent_deployment = None
    if deployment:
        recent_deployment = {
            "version": deployment.version,
            "changes": deployment.changes,
            "minutes_before_incident": minutes_before_incident(deployment, incident),
        }

    return {
        "current_incident": current,
        "recent_deployment": recent_deployment,
        "similar_incidents": [
            {
                "incident_id": s["incident_code"],
                "service": s["service_name"],
                "similarity_score": s["similarity_score"],
                "symptoms": s["symptoms"],
                "root_cause": s["root_cause"],
                "lesson": s["key_lesson"],
                "actions": [
                    {
                        "type": a["type"],
                        "outcome": a["outcome"]["status"] if a["outcome"] else "unrecorded",
                        "notes": a["outcome"]["notes"] if a["outcome"] else "",
                    }
                    for a in s["actions"]
                ],
            }
            for s in similar
        ],
        "_similar_raw": similar,
    }


def fallback_recommendation(context: dict) -> dict:
    current = context["current_incident"]
    similar = context["_similar_raw"]
    has_recent_deployment = current["has_recent_deployment"]

    action_records: dict[str, list[tuple[str, str]]] = {}
    for s in similar:
        for a in s["actions"]:
            if a["outcome"]:
                action_records.setdefault(a["type"], []).append((a["outcome"]["status"], s["incident_code"]))

    warnings = []
    for atype, records in action_records.items():
        for status, code in records:
            if status in ("temporary", "failed"):
                label = ACTION_LABELS.get(atype, atype)
                warnings.append(f"{label} was only {status} in {code}; do not treat it as a permanent fix.")

    def evidence_for(atype: str, wanted_status: str | None = None) -> list[str]:
        codes = []
        for status, code in action_records.get(atype, []):
            if wanted_status is None or status == wanted_status:
                codes.append(code)
        return codes

    rollback_success = evidence_for("rollback_deployment", "successful")
    db_symptom_present = _has_db_signal(current["metrics"]) or any(
        "db" in sym.lower() or "connection" in sym.lower() for sym in current["symptoms"]
    )

    if has_recent_deployment and rollback_success:
        evidence = list(dict.fromkeys(rollback_success + evidence_for("restart_service", "temporary")))
        return {
            "recommended_action": "rollback_deployment",
            "target": f"{current['service']}:{context['recent_deployment']['version']}",
            "reason": (
                "A deployment landed shortly before this incident and closely matching prior "
                "deployment-related incidents were resolved by rolling back."
            ),
            "evidence": evidence or [current.get("service", "")],
            "warnings": warnings,
            "alternative_actions": [
                a for a in ("inspect_db_connections", "increase_connection_pool") if a != "rollback_deployment"
            ],
            "risk": "medium",
        }

    if not has_recent_deployment and db_symptom_present:
        evidence = list(
            dict.fromkeys(
                evidence_for("increase_connection_pool") + evidence_for("restart_service") + [s["incident_id"] for s in context["similar_incidents"]][:2]
            )
        )
        return {
            "recommended_action": "inspect_db_connections",
            "target": current["service"],
            "reason": (
                "No recent deployment is associated with this incident, so a bad release is unlikely. "
                "DB connection saturation persists, which points to long-running queries or a connection leak."
            ),
            "evidence": evidence,
            "warnings": warnings,
            "alternative_actions": ["investigate_query_performance", "increase_connection_pool"],
            "risk": "medium",
        }

    priority = ["successful", "partial", "temporary", "failed"]
    best_action, best_status, best_code = None, None, None
    for atype, records in action_records.items():
        for status, code in records:
            rank = priority.index(status) if status in priority else len(priority)
            if best_status is None or rank < priority.index(best_status):
                best_action, best_status, best_code = atype, status, code

    if best_action:
        return {
            "recommended_action": best_action,
            "target": current["service"],
            "reason": f"The most effective historically evidenced action for this symptom pattern was {ACTION_LABELS.get(best_action, best_action).lower()} ({best_status} in {best_code}).",
            "evidence": [best_code],
            "warnings": warnings,
            "alternative_actions": [a for a in action_records if a != best_action][:2],
            "risk": "medium" if best_status == "successful" else "high",
        }

    return {
        "recommended_action": "no_action",
        "target": current["service"],
        "reason": "No closely matching historical incidents were found. Escalate for manual investigation using available runbooks.",
        "evidence": [],
        "warnings": [],
        "alternative_actions": [],
        "risk": "high",
    }


def _build_hindsight_query(context: dict) -> str:
    current = context["current_incident"]
    metrics_text = ", ".join(f"{k}={v}" for k, v in current["metrics"].items())
    deployment_text = (
        f"Deployment {context['recent_deployment']['version']} landed "
        f"{context['recent_deployment']['minutes_before_incident']} minutes before this incident."
        if context.get("recent_deployment")
        else "No recent deployment is associated with this incident."
    )
    return (
        f"New {current['severity']} incident on {current['service']}: {', '.join(current['symptoms'])}. "
        f"Metrics: {metrics_text}. {deployment_text} "
        "What single remediation action do you recommend, and does any similar past action only "
        "partially work, provide temporary relief, or fail outright? In the 'evidence' field, cite "
        "ONLY incident codes in the exact form INC-XXX (e.g. INC-087) taken from the incidents listed "
        "below — do not put symptom descriptions or free text in 'evidence'."
    )


def _build_hindsight_context_text(context: dict) -> str:
    return "Known similar incidents and their action outcomes (evidence codes in brackets):\n" + json.dumps(
        context["similar_incidents"], indent=2
    )


def _validate_candidate(candidate: dict | None, context: dict) -> dict | None:
    """Shared guardrail for any LLM-shaped source (Hindsight reflect or direct Groq call).
    Returns None if the candidate should be rejected so the caller tries the next tier -
    an LLM response can never bypass backend validation."""
    if not candidate:
        return None
    required = {"recommended_action", "target", "reason", "evidence", "warnings", "alternative_actions", "risk"}
    if not required.issubset(candidate.keys()):
        return None
    if candidate["recommended_action"] not in ALLOWED_ACTIONS:
        return None
    if candidate["risk"] not in ("low", "medium", "high"):
        return None

    has_recent_deployment = context["current_incident"]["has_recent_deployment"]
    if candidate["recommended_action"] == "rollback_deployment" and not has_recent_deployment:
        # Never blindly repeat a deployment-era fix when there is no deployment signal.
        return None

    candidate = dict(candidate)
    known_codes = {s["incident_id"] for s in context["similar_incidents"]}
    raw_evidence = candidate.get("evidence", [])
    # Not every source (esp. Hindsight reflect, whose evidence field is LLM-written free
    # text) reliably cites incident codes in the 'evidence' array itself. Ground evidence
    # in known codes wherever they're mentioned - evidence field, reason, or warnings -
    # so confidence scoring always has something real to compute against when the
    # underlying incidents were genuinely referenced.
    scan_text = " ".join(raw_evidence) + " " + candidate.get("reason", "") + " " + " ".join(candidate.get("warnings", []))
    mentioned_codes = [code for code in INCIDENT_CODE_RE.findall(scan_text) if code in known_codes]
    direct_matches = [e for e in raw_evidence if e in known_codes]
    grounded_evidence = list(dict.fromkeys(direct_matches + mentioned_codes))
    candidate["evidence"] = grounded_evidence or raw_evidence
    candidate["alternative_actions"] = [
        a for a in candidate.get("alternative_actions", []) if a in ALLOWED_ACTIONS
    ]
    return candidate


def build_recommendation(context: dict) -> tuple[dict, str]:
    """Three-tier recommendation source, most-capable first, each validated the same way:
    Hindsight reflect (the memory-grounded reasoning layer) -> direct Groq call ->
    deterministic rule-based fallback. The demo stays reliable even if either external
    integration is unavailable."""
    hindsight_candidate = hindsight_memory.reflect_recommendation(
        context["current_incident"]["service"],
        _build_hindsight_query(context),
        _build_hindsight_context_text(context),
    )
    validated = _validate_candidate(hindsight_candidate, context)
    if validated:
        return validated, "hindsight"

    llm_candidate = llm_generate(context)
    validated = _validate_candidate(llm_candidate, context)
    if validated:
        return validated, "llm"

    return fallback_recommendation(context), "deterministic_fallback"


def compute_confidence(context: dict, recommendation: dict) -> tuple[int, list[dict]]:
    current = context["current_incident"]
    similar_by_code = {s["incident_code"]: s for s in context["_similar_raw"]}
    evidence_incidents = [similar_by_code[e] for e in recommendation["evidence"] if e in similar_by_code]

    breakdown = []

    if evidence_incidents:
        matching = sum(1 for e in evidence_incidents if e["service_name"] == current["service"])
        same_service_contrib = round(20 * matching / len(evidence_incidents))
    else:
        same_service_contrib = 0
    breakdown.append(
        {
            "signal": "Same service",
            "weight": 20,
            "matched": same_service_contrib == 20,
            "contribution": same_service_contrib,
            "explanation": f"{len(evidence_incidents)} evidence incident(s) checked against service '{current['service']}'.",
        }
    )

    if evidence_incidents:
        sym_scores = [symptom_similarity(current["symptoms"], e["symptoms"]) for e in evidence_incidents]
        sym_contrib = round(20 * (sum(sym_scores) / len(sym_scores)))
    else:
        sym_contrib = 0
    breakdown.append(
        {
            "signal": "Symptom similarity",
            "weight": 20,
            "matched": sym_contrib >= 14,
            "contribution": sym_contrib,
            "explanation": "Overlap between current symptoms and evidence incident symptoms.",
        }
    )

    if evidence_incidents:
        met_scores = [metric_similarity(current["metrics"], e.get("metrics_before", {}) or {}) for e in evidence_incidents]
        met_contrib = round(20 * (sum(met_scores) / len(met_scores))) if met_scores else 0
    else:
        met_contrib = 10
    breakdown.append(
        {
            "signal": "Metric similarity",
            "weight": 20,
            "matched": met_contrib >= 14,
            "contribution": met_contrib,
            "explanation": "Closeness of current error rate/latency/DB metrics to evidence incidents.",
        }
    )

    action = recommendation["recommended_action"]
    if action == "rollback_deployment":
        deploy_contrib = 20 if current["has_recent_deployment"] else 4
    elif current["has_recent_deployment"]:
        deploy_contrib = 10
    else:
        deploy_contrib = 20
    breakdown.append(
        {
            "signal": "Recent deployment signal",
            "weight": 20,
            "matched": deploy_contrib >= 14,
            "contribution": deploy_contrib,
            "explanation": (
                f"Recent deployment present: {current['has_recent_deployment']}; recommended action: {action}."
            ),
        }
    )

    outcome_map = {"successful": 20, "partial": 12, "temporary": 6, "failed": 2}
    matching_outcomes = [
        outcome_map.get(a["outcome"]["status"], 8)
        for e in evidence_incidents
        for a in e.get("actions", [])
        if a["type"] == action and a["outcome"]
    ]
    outcome_contrib = round(sum(matching_outcomes) / len(matching_outcomes)) if matching_outcomes else 8
    breakdown.append(
        {
            "signal": "Historical action/outcome relevance",
            "weight": 20,
            "matched": outcome_contrib >= 14,
            "contribution": outcome_contrib,
            "explanation": "How well the recommended action performed when tried in evidence incidents.",
        }
    )

    total = sum(item["contribution"] for item in breakdown)
    return min(100, total), breakdown


def generate_recommendation(db: Session, incident: Incident) -> dict:
    context = build_reasoning_context(db, incident)
    recommendation, source = build_recommendation(context)
    confidence, breakdown = compute_confidence(context, recommendation)

    action = Action(
        incident_id=incident.id,
        type=recommendation["recommended_action"],
        description=recommendation["reason"],
        status=ActionStatus.PENDING.value,
        recommendation={**recommendation, "confidence": confidence, "source": source},
    )
    db.add(action)
    db.commit()
    db.refresh(action)

    return {
        "incident_id": incident.id,
        "action_id": action.id,
        "recommended_action": recommendation["recommended_action"],
        "target": recommendation["target"],
        "reason": recommendation["reason"],
        "evidence": recommendation["evidence"],
        "warnings": recommendation["warnings"],
        "alternative_actions": recommendation["alternative_actions"],
        "risk": recommendation["risk"],
        "confidence": confidence,
        "confidence_breakdown": breakdown,
        "source": source,
    }

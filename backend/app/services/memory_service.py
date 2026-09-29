from sqlalchemy.orm import Session

from app.models.models import Incident, Service
from app.services.similarity_service import score_incident_pair, similarity_label
from app.services.incident_service import incident_code, serialize_action
from app.ai import hindsight_memory


def _build_recall_query(incident: Incident) -> str:
    symptom_text = ", ".join(incident.symptoms) if incident.symptoms else "unspecified symptoms"
    parts = [f"Production incident with symptoms: {symptom_text}."]
    if incident.metrics_before:
        metrics_text = ", ".join(f"{k}={v}" for k, v in incident.metrics_before.items())
        parts.append(f"Current metrics: {metrics_text}.")
    return " ".join(parts)


def _serialize_candidate(db: Session, candidate: Incident, service_name: str, score: int, source: str) -> dict:
    lesson = candidate.lessons[0] if candidate.lessons else None
    return {
        "incident_id": candidate.id,
        "incident_code": incident_code(candidate.id),
        "service_name": service_name,
        "service_id": candidate.service_id,
        "similarity_score": score,
        "similarity_label": similarity_label(score),
        "severity": candidate.severity,
        "symptoms": candidate.symptoms,
        "metrics_before": candidate.metrics_before,
        "root_cause": candidate.root_cause,
        "key_lesson": lesson.lesson_text if lesson else None,
        "actions": [serialize_action(a) for a in candidate.actions],
        "retrieval_source": source,
    }


def _get_similar_via_hindsight(db: Session, incident: Incident, service: Service, limit: int) -> list[dict] | None:
    if not hindsight_memory.is_configured():
        return None

    results = hindsight_memory.recall_similar_incidents(service.name, _build_recall_query(incident))
    if not results:
        return None

    output = []
    seen_ids = set()
    for result in results:
        code = (result.metadata or {}).get("incident_code")
        if not code or not code.startswith("INC-"):
            continue
        try:
            candidate_id = int(code[4:])
        except ValueError:
            continue
        if candidate_id == incident.id or candidate_id in seen_ids:
            continue
        candidate = db.query(Incident).get(candidate_id)
        if not candidate:
            continue
        seen_ids.add(candidate_id)

        final_score = result.scores.final if result.scores else 0.5
        score = round(max(0.0, min(1.0, final_score)) * 100)
        entry = _serialize_candidate(db, candidate, service.name, score, source="hindsight")
        entry["recall_text"] = result.text
        output.append(entry)
        if len(output) >= limit:
            break

    return output or None


def _get_similar_via_structured_scoring(db: Session, incident: Incident, limit: int) -> list[dict]:
    candidates = db.query(Incident).filter(Incident.id != incident.id).all()
    scored = []
    for candidate in candidates:
        score = score_incident_pair(
            incident.symptoms,
            incident.metrics_before,
            incident.service_id,
            candidate.symptoms,
            candidate.metrics_before,
            candidate.service_id,
        )
        scored.append((score, candidate))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = [pair for pair in scored if pair[0] > 0][:limit]

    results = []
    for score, candidate in top:
        service = db.query(Service).get(candidate.service_id)
        results.append(_serialize_candidate(db, candidate, service.name, score, source="structured"))
    return results


def get_similar_incidents(db: Session, incident: Incident, limit: int = 5) -> list[dict]:
    """Similar-incident retrieval. Hindsight recall is the primary source; the
    deterministic structured scorer is the fallback when Hindsight isn't configured
    or returns nothing usable."""
    service = db.query(Service).get(incident.service_id)
    hindsight_results = _get_similar_via_hindsight(db, incident, service, limit)
    if hindsight_results is not None:
        return hindsight_results
    return _get_similar_via_structured_scoring(db, incident, limit)

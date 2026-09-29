"""Deterministic structured similarity scoring.

Confidence must be computed in application code, not invented by the LLM (spec
section 14). This module provides the shared scoring primitives used both for
ranking "similar incidents" and for building the recommendation confidence
breakdown in recommendation_service.py.
"""
from app.ai.embeddings import embed_incident, cosine_similarity

NORMAL_RANGES = {
    "error_rate": 2.0,       # percent
    "latency_ms": 500.0,
    "db_connections_pct": 70.0,
}

RECENT_DEPLOYMENT_WINDOW_MINUTES = 60


def normalize_symptom(s: str) -> str:
    return s.strip().lower()


def symptom_similarity(current: list[str], historical: list[str]) -> float:
    a = {normalize_symptom(s) for s in current}
    b = {normalize_symptom(s) for s in historical}
    if not a or not b:
        return 0.0
    intersection = a & b
    union = a | b
    return len(intersection) / len(union) if union else 0.0


def metric_similarity(current: dict, historical: dict) -> float:
    shared_keys = set(current.keys()) & set(historical.keys())
    if not shared_keys:
        return 0.3  # neutral-low: nothing directly comparable
    scores = []
    for key in shared_keys:
        c, h = float(current[key]), float(historical[key])
        denom = max(abs(c), abs(h), 1.0)
        scores.append(1.0 - min(1.0, abs(c - h) / denom))
    return sum(scores) / len(scores)


def similarity_label(score: int) -> str:
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def score_incident_pair(
    current_symptoms: list[str],
    current_metrics: dict,
    current_service_id: int,
    historical_symptoms: list[str],
    historical_metrics: dict,
    historical_service_id: int,
) -> int:
    same_service = 1.0 if current_service_id == historical_service_id else 0.0
    sym_sim = symptom_similarity(current_symptoms, historical_symptoms)
    met_sim = metric_similarity(current_metrics, historical_metrics)
    embedding_sim = cosine_similarity(
        embed_incident(current_symptoms, None), embed_incident(historical_symptoms, None)
    )
    score = (0.25 * same_service) + (0.35 * sym_sim) + (0.25 * met_sim) + (0.15 * embedding_sim)
    return round(score * 100)

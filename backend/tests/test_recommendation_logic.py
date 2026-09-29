"""Unit tests for the deterministic reasoning layer (no DB required).

These exercise the core behaviors we test for: known pattern retrieval,
temporary/failed-action warnings, context-aware recommendation change, and
outcome classification.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.recommendation_service import fallback_recommendation
from app.services.outcome_service import classify_outcome
from app.ai.llm_client import generate_recommendation


PAYMENT_SIMILAR_RAW = [
    {
        "incident_code": "INC-087",
        "service_name": "payment-service",
        "symptoms": ["5xx errors", "high latency", "db connection saturation"],
        "metrics_before": {"error_rate": 19.1, "latency_ms": 2500, "db_connections_pct": 94},
        "root_cause": "Deployment v2.3.0 introduced a connection leak causing DB exhaustion.",
        "actions": [
            {"type": "rollback_deployment", "outcome": {"status": "successful", "notes": "Restored stable metrics."}}
        ],
    },
    {
        "incident_code": "INC-064",
        "service_name": "payment-service",
        "symptoms": ["5xx errors", "high latency", "db connection saturation"],
        "metrics_before": {"error_rate": 17.5, "latency_ms": 2300, "db_connections_pct": 90},
        "root_cause": "Transient resource exhaustion.",
        "actions": [
            {"type": "restart_service", "outcome": {"status": "temporary", "notes": "Recovered for ~10 minutes."}}
        ],
    },
    {
        "incident_code": "INC-041",
        "service_name": "payment-service",
        "symptoms": ["5xx errors", "elevated latency"],
        "metrics_before": {"error_rate": 9.2, "latency_ms": 1400, "db_connections_pct": 75},
        "root_cause": "Connection pool sizing insufficient.",
        "actions": [
            {"type": "increase_connection_pool", "outcome": {"status": "partial", "notes": "Reduced errors."}}
        ],
    },
]


def _context(has_recent_deployment: bool, similar=PAYMENT_SIMILAR_RAW):
    return {
        "current_incident": {
            "service": "payment-service",
            "severity": "SEV-1",
            "symptoms": ["5xx errors", "high latency", "db connection saturation"],
            "metrics": {"error_rate": 18.4, "latency_ms": 2400, "db_connections_pct": 96},
            "has_recent_deployment": has_recent_deployment,
        },
        "recent_deployment": {"version": "v2.4.1", "changes": "", "minutes_before_incident": 8}
        if has_recent_deployment
        else None,
        "similar_incidents": [
            {
                "incident_id": s["incident_code"],
                "service": s["service_name"],
                "symptoms": s["symptoms"],
                "root_cause": s["root_cause"],
                "actions": [{"type": a["type"], "outcome": a["outcome"]["status"]} for a in s["actions"]],
            }
            for s in similar
        ],
        "_similar_raw": similar,
    }


def test_known_pattern_recommends_rollback_with_temporary_warning():
    ctx = _context(has_recent_deployment=True)
    rec = fallback_recommendation(ctx)
    assert rec["recommended_action"] == "rollback_deployment"
    assert any("temporary" in w.lower() for w in rec["warnings"])
    assert "INC-087" in rec["evidence"]


def test_context_change_avoids_blind_rollback_repeat():
    ctx = _context(has_recent_deployment=False)
    rec = fallback_recommendation(ctx)
    assert rec["recommended_action"] != "rollback_deployment"
    assert rec["recommended_action"] == "inspect_db_connections"


def test_no_similar_incidents_falls_back_to_manual_investigation():
    ctx = _context(has_recent_deployment=True, similar=[])
    rec = fallback_recommendation(ctx)
    assert rec["recommended_action"] == "no_action"
    assert rec["evidence"] == []


def test_llm_unavailable_returns_none_without_api_key(monkeypatch):
    monkeypatch.setattr("app.ai.llm_client.settings.groq_api_key", "")
    ctx = _context(has_recent_deployment=True)
    assert generate_recommendation(ctx) is None


def test_classify_outcome_successful_when_metrics_normalize():
    status, _ = classify_outcome(
        "rollback_deployment",
        {"error_rate": 18.4, "latency_ms": 2400, "db_connections_pct": 96},
        {"error_rate": 1.1, "latency_ms": 260, "db_connections_pct": 30},
        None,
    )
    assert status == "successful"


def test_classify_outcome_temporary_when_action_regresses():
    status, _ = classify_outcome(
        "restart_service",
        {"error_rate": 18.4, "latency_ms": 2400, "db_connections_pct": 96},
        {"error_rate": 2.0, "latency_ms": 400, "db_connections_pct": 40},
        10,
    )
    assert status == "temporary"


def test_classify_outcome_failed_when_no_improvement():
    status, _ = classify_outcome(
        "restart_service",
        {"error_rate": 18.4, "latency_ms": 2400, "db_connections_pct": 96},
        {"error_rate": 18.0, "latency_ms": 2380, "db_connections_pct": 95},
        None,
    )
    assert status == "failed"

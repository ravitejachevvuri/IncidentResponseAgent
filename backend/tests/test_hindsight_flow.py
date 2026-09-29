"""End-to-end tests for the Hindsight-backed recommendation flow.

Hindsight itself isn't reachable in CI/local runs without real credentials, so
these tests monkeypatch the Hindsight client with a fake that returns
realistic SDK response objects. This exercises the full plumbing: bank
derivation, retain() metadata round-tripping through recall(), and reflect()'s
structured_output flowing through the same backend guardrails as every other
recommendation source.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy import create_engine, text as sqltext
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

import app.db as db_module

SCENARIO_1 = {
    "service_name": "payment-service",
    "severity": "SEV-1",
    "symptoms": ["5xx errors", "high latency", "db connection saturation"],
    "metrics": {"error_rate": 18.4, "latency_ms": 2400, "db_connections_pct": 96},
    "recent_deployment": {"version": "v2.4.1", "changes": "Updated payment retry logic", "minutes_before": 8},
}


class FakeHindsightClient:
    """Stands in for hindsight_client.Hindsight; always recommends rollback so
    tests can prove the *backend* guardrail (not the LLM) enforces context-awareness."""

    def __init__(self):
        self.retained = []

    def create_bank(self, **kwargs):
        return None

    def delete_bank(self, bank_id):
        return None

    def close(self):
        return None

    def retain(self, **kwargs):
        self.retained.append(kwargs)
        return None

    def recall(self, bank_id, query, **kwargs):
        from hindsight_client import RecallResponse, RecallResult

        return RecallResponse(
            results=[
                RecallResult(
                    id="1",
                    text="INC-087: rollback fixed a deployment-related DB exhaustion incident.",
                    metadata={"incident_code": "INC-087"},
                    scores={"final": 0.95},
                ),
                RecallResult(
                    id="2",
                    text="INC-064: restart only helped for ~10 minutes before symptoms returned.",
                    metadata={"incident_code": "INC-064"},
                    scores={"final": 0.9},
                ),
            ]
        )

    def reflect(self, bank_id, query, **kwargs):
        from hindsight_client import ReflectResponse

        return ReflectResponse(
            text="Roll back the deployment.",
            structured_output={
                "recommended_action": "rollback_deployment",
                "target": "payment-service:v2.4.1",
                "reason": "Hindsight memory shows deployment-related incidents were resolved by rollback.",
                "evidence": ["INC-087", "INC-064"],
                "warnings": ["Restart service was only temporary in INC-064."],
                "alternative_actions": ["inspect_db_connections"],
                "risk": "medium",
            },
        )


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    db_module.engine = engine
    db_module.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    import seed.seed_data as seed_data

    orig_reset = seed_data.reset_and_seed

    def patched_reset(db):
        orig_execute = db.execute

        def safe_execute(stmt, *a, **kw):
            if isinstance(stmt, type(sqltext(""))) and "setval" in str(stmt):
                return None
            return orig_execute(stmt, *a, **kw)

        db.execute = safe_execute
        orig_reset(db)

    seed_data.reset_and_seed = patched_reset

    from app.main import app
    from app.db import Base

    Base.metadata.create_all(bind=engine)

    import app.ai.hindsight_memory as hm

    fake = FakeHindsightClient()
    original_get_client = hm.get_client
    hm.get_client = lambda: fake
    hm._banks_ready.clear()
    hm.settings.hindsight_api_key = "fake-key"
    hm.settings.hindsight_base_url = "http://fake"

    test_client = TestClient(app)
    test_client.post("/api/demo/reset")
    yield test_client, fake

    hm.get_client = original_get_client
    hm.settings.hindsight_api_key = ""
    hm.settings.hindsight_base_url = ""


def test_health_reports_hindsight_configured(client):
    test_client, _ = client
    response = test_client.get("/api/health")
    assert response.json()["hindsight_configured"] is True


def test_similar_incidents_sourced_from_hindsight_recall(client):
    test_client, _ = client
    incident = test_client.post("/api/incidents", json=SCENARIO_1).json()
    similar = test_client.get(f"/api/incidents/{incident['id']}/similar").json()
    assert similar
    assert all(s["retrieval_source"] == "hindsight" for s in similar)
    assert any(s["incident_code"] == "INC-087" for s in similar)


def test_recommendation_uses_hindsight_reflect(client):
    test_client, _ = client
    incident = test_client.post("/api/incidents", json=SCENARIO_1).json()
    rec = test_client.post(f"/api/incidents/{incident['id']}/recommendation").json()
    assert rec["source"] == "hindsight"
    assert rec["recommended_action"] == "rollback_deployment"
    assert any("temporary" in w.lower() for w in rec["warnings"])


def test_guardrail_overrides_hindsight_when_no_deployment_signal(client):
    """The fake always recommends rollback. Once scenario 1 is fully resolved (which
    marks its deployment rolled_back) and scenario 2 runs with no deployment field,
    the backend must reject Hindsight's rollback call, not the LLM."""
    test_client, _ = client
    incident1 = test_client.post("/api/incidents", json=SCENARIO_1).json()
    rec1 = test_client.post(f"/api/incidents/{incident1['id']}/recommendation").json()
    action_id = rec1["action_id"]
    test_client.post(f"/api/actions/{action_id}/approve", json={"approved_by": "test"})
    test_client.post(f"/api/actions/{action_id}/simulate")
    test_client.post(f"/api/actions/{action_id}/outcome")

    scenario_2 = {k: v for k, v in SCENARIO_1.items() if k != "recent_deployment"}
    incident2 = test_client.post("/api/incidents", json=scenario_2).json()
    assert incident2["recent_deployment"] is None

    rec2 = test_client.post(f"/api/incidents/{incident2['id']}/recommendation").json()
    assert rec2["recommended_action"] != "rollback_deployment"
    assert rec2["source"] == "deterministic_fallback"


def test_retain_called_on_outcome_write_back(client):
    test_client, fake = client
    before_count = len(fake.retained)
    incident = test_client.post("/api/incidents", json=SCENARIO_1).json()
    rec = test_client.post(f"/api/incidents/{incident['id']}/recommendation").json()
    action_id = rec["action_id"]
    test_client.post(f"/api/actions/{action_id}/approve", json={"approved_by": "test"})
    test_client.post(f"/api/actions/{action_id}/simulate")
    test_client.post(f"/api/actions/{action_id}/outcome")
    assert len(fake.retained) > before_count

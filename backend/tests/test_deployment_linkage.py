"""Regression test for the deployment-attribution bug: get_recent_deployment() used to
re-derive "the recent deployment" via a fuzzy timing window every time it was called,
which could attribute the wrong deployment once multiple incidents/deployments existed
close together on the same service. Incidents now capture an explicit FK to their own
deployment at creation time (get_incident_deployment), so this can no longer drift.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

import app.db as db_module


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    db_module.engine = engine
    db_module.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    from app.main import app
    from app.db import Base

    Base.metadata.create_all(bind=engine)
    return TestClient(app)


def _create_with_deployment(client, version, minutes_before=8):
    return client.post(
        "/api/incidents",
        json={
            "service_name": "payment-service",
            "severity": "SEV-1",
            "symptoms": ["5xx errors", "high latency"],
            "metrics": {"error_rate": 18.0, "latency_ms": 2200},
            "recent_deployment": {"version": version, "changes": "x", "minutes_before": minutes_before},
        },
    ).json()


def test_rollback_marks_only_its_own_deployment(client):
    """Two incidents on the same service, each with their own deployment created close
    together (the exact condition that used to trigger the bug). Rolling back the first
    must not touch the second's deployment, and vice versa."""
    incident_a = _create_with_deployment(client, "v1.0.0")
    incident_b = _create_with_deployment(client, "v1.0.1")

    assert incident_a["recent_deployment"]["version"] == "v1.0.0"
    assert incident_b["recent_deployment"]["version"] == "v1.0.1"

    rec_a = client.post(f"/api/incidents/{incident_a['id']}/recommendation").json()
    action_a = rec_a["action_id"]

    # Force a rollback_deployment action regardless of what was recommended, to
    # deterministically exercise the rolled_back-marking code path.
    from app.db import SessionLocal
    from app.models.models import Action

    db = SessionLocal()
    db.query(Action).filter(Action.id == action_a).update({"type": "rollback_deployment"})
    db.commit()
    db.close()

    client.post(f"/api/actions/{action_a}/approve", json={"approved_by": "test"})
    client.post(f"/api/actions/{action_a}/simulate")
    client.post(f"/api/actions/{action_a}/outcome")

    incident_a_after = client.get(f"/api/incidents/{incident_a['id']}").json()
    incident_b_after = client.get(f"/api/incidents/{incident_b['id']}").json()

    assert incident_a_after["recent_deployment"] is None, (
        "incident A's own deployment should now be rolled back and no longer shown as recent"
    )
    assert incident_b_after["recent_deployment"] is not None, (
        "incident B's unrelated deployment must not be affected by resolving incident A"
    )
    assert incident_b_after["recent_deployment"]["version"] == "v1.0.1"
